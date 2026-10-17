"""Bounded Flash tool loop with persistent conversations and versioned scene-graph edits."""
import json
import logging
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from app.core import db, storage
from app.core.config import use_stubs
from app.core.validation import validate_contract
from app.brand.lint import lint_design
from app.brand.fonts import BrandSetupError, FALLBACK_NOTICE, require_design_kit
from app.decompose import pipeline
from app.generate import common as c, variants, chat as edits
from app.llm import deepseek
from .tools import TOOLS, SYSTEM

ACTIVE = set()
THREAD_LOCK = threading.Lock()
MAX_STEPS = 15
log = logging.getLogger(__name__)

class SplitFailedError(ValueError):
    """Stop the turn when a split fails instead of asking Flash to repeat it."""

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def message(role, text, attachments=(), designs=(), steps=()):
    return validate_contract('Message', {'id':'msg_' + uuid4().hex, 'role':role, 'text':text,
        'attachmentAssetIds':list(attachments), 'designIds':list(designs), 'steps':list(steps), 'createdAt':now()})

def owned_design(ws, design_id):
    design = db.get('Design', design_id)
    if design['workspaceId'] != ws:
        raise ValueError('Design is outside this workspace')
    return validate_contract('Design', design)

def owned_asset(ws, asset_id):
    asset = storage.get_asset(asset_id)
    if asset.workspaceId != ws:
        raise ValueError('Asset is outside this workspace')
    return asset

class Session:
    def __init__(self, job_id, thread, text, attachments, focus):
        self.job_id, self.thread, self.ws = job_id, thread, thread['workspaceId']
        self.kit = storage.get_brand_kit(self.ws)
        require_design_kit(self.kit)
        self.text, self.attachments, self.focus = text, attachments, focus
        self.aliases, self.outputs, self.sources, self.changes = {}, {}, {}, {}
        self.allowed = set(focus)
        self.reply_text = ''
        self.calls = 0
        self.split_failures = {}
        for msg in thread['messages'][-20:]:
            self.allowed.update(msg['designIds'])

    def step(self, text):
        with c.LOCK:
            job = c.JOBS[self.job_id]
            job.setdefault('steps', []).append(text)
            job['progress'] = text

    def design(self, design_id):
        if design_id not in self.allowed:
            raise ValueError('Design was not mentioned in this thread or focused')
        return owned_design(self.ws, self.aliases.get(design_id, design_id))

    def publish(self, design):
        design = validate_contract('Design', design)
        db.put('Design', design['id'], self.ws, design)
        self.allowed.add(design['id'])
        self.outputs[design.get('label') or design['id']] = design
        with c.LOCK:
            c.JOBS[self.job_id]['designs'] = list(self.outputs.values())

    def context(self):
        designs = [self.design(i) for i in sorted(self.allowed)]
        unique = {d['id']:d for d in designs}
        latest = {}
        # Thread order resolves equal-version branches; named labels always point to their newest version.
        ids = [i for m in self.thread['messages'][-20:] for i in m['designIds']] + list(self.outputs_id()) + self.focus
        for i in ids:
            if i in self.allowed:
                d = self.design(i)
                if d.get('label'):
                    previous = latest.get(d['label'])
                    if not previous or d.get('version',1) >= self.design(previous).get('version',1):
                        latest[d['label']] = d['id']
        return {'brandKit':self.kit.model_dump(mode='json', exclude_unset=True),
                'assets':[{'id':a.id,'kind':a.kind,'source':a.source,'caption':a.caption,'filename':a.filename,'tags':a.tags}
                          for a in storage.list_assets(self.ws)],
                'messages':self.thread['messages'][-20:], 'designs':list(unique.values()), 'latestByLabel':latest,
                'focusDesignIds':[self.aliases.get(i,i) for i in self.focus], 'attachmentAssetIds':self.attachments}

    def summary(self):
        return '\n'.join(f"{d.get('label',d['name'])} v{d.get('version',1)}: " +
                         '; '.join(self.changes.get(d.get('label') or d['id'], ['updated'])) + '.'
                         for d in self.outputs.values())

    def outputs_id(self):
        return [d['id'] for d in self.outputs.values()]

    def apply(self, original, ops):
        working = original
        for op in ops:
            edits.check_op(working, self.kit, op)
            working = c.apply_ops(working, [op])
        working, issues = c.lint_fix(working, self.kit, rounds=2)
        # Several operations in one turn edit the same new version, preserving the original parent.
        if original['id'] not in self.outputs_id():
            working.update(id='des_' + uuid4().hex, parentId=original['id'], version=original.get('version',1)+1)
            working.setdefault('label', original.get('label', original['name']))
            self.aliases[original['id']] = working['id']
        self.publish(working)
        return {'design':working, 'lintErrors':sum(v.severity == 'error' for v in issues)}

    def split(self, asset_id):
        asset = owned_asset(self.ws, asset_id)
        if asset.kind != 'sample' or asset.source != 'upload':
            raise ValueError('Only uploaded samples can be split')
        if asset_id in self.sources:
            return self.design(self.sources[asset_id])
        if asset_id in self.split_failures:
            raise SplitFailedError(self.split_failures[asset_id])
        self.step('Reading the reference and splitting it into editable layers')
        if use_stubs():
            from app.core.fixtures import variant_designs
            source = variant_designs(self.ws, 1)[0]
            db.put('Design',source['id'],self.ws,source)
        else:
            try:
                pipeline.run_decompose(self.job_id, self.ws, asset)
                source = c.JOBS[self.job_id]['designs'][-1]
            except Exception as exc:
                log.exception('Split failed for sample %s in workspace %s',asset_id,self.ws)
                detail = str(exc) if isinstance(exc,BrandSetupError) else 'The layer splitter could not finish. Your uploaded image is saved; retry this request without uploading it again.'
                self.split_failures[asset_id] = detail
                raise SplitFailedError(detail) from exc
        self.sources[asset_id] = source['id']
        self.allowed.add(source['id'])
        with c.LOCK:
            c.JOBS[self.job_id]['designs'] = list(self.outputs.values())
        return source

    def options(self, args):
        if args.get('n',4) != 4: raise ValueError('Studio generates four options')
        source = self.design(args['sourceDesignId']) if args.get('sourceDesignId') else self.split(args['assetId'])
        sample_id = next((a for a,d in self.sources.items() if d == source['id']), None)
        if not sample_id:
            sample_id = next((owned_asset(self.ws,l['assetId']).meta.get('sampleAssetId') for l in source['layers']
                              if l['type']=='image' and owned_asset(self.ws,l['assetId']).meta.get('sampleAssetId')), None)
        # Generation from an existing option uses its JSON to form a spec; no image export is sent to a model.
        sample = owned_asset(self.ws,sample_id) if sample_id else None
        self.step('Planning four options with your brand, message and layout')
        before = len(c.JOBS[self.job_id]['designs'])
        if use_stubs():
            from app.core.fixtures import variant_designs
            designs = variant_designs(self.ws,4)
        else:
            variants.run_variants(self.job_id, self.ws, sample, args.get('brief') or self.text,
                                  source_design=source, studio=True)
            designs = c.JOBS[self.job_id]['designs'][before:]
        for i, design in enumerate(designs):
            design.update(label=f'Option {chr(65+i)}', version=1)
            self.publish(design)
            self.changes[design['label']] = [design['name'].split(': ',1)[-1][:80]]
        self.step('Four editable options are ready')
        return {'designs':designs}

    def execute(self, name, args):
        if name == 'reply':
            self.reply_text = str(args['text']).strip()
            return {'reply':self.reply_text}
        if name == 'search_assets':
            self.step('Searching your approved brand assets')
            words = set(re.findall(r'\w+',args['query'].lower()))
            assets = [a for a in storage.list_assets(self.ws,args.get('kind')) if a.source=='brand_asset']
            def score(a): return len(words & set(re.findall(r'\w+', ' '.join([a.filename,a.caption,*a.tags]).lower())))
            assets = sorted(assets,key=score,reverse=True)
            return {'assets':[a.model_dump(mode='json') for a in assets[:12] if score(a)>0]}
        if name == 'split_into_layers': return {'design':self.split(args['assetId'])}
        if name == 'generate_options': return self.options(args)
        design = self.design(args['designId'])
        if name == 'run_lint':
            self.step(f"Checking {design.get('label',design['name'])} against your brand")
            return {'violations':[v.model_dump(mode='json') for v in lint_design(design,self.kit)]}
        self.step(f"{design.get('label',design['name'])}: {name.replace('_',' ')}")
        if name in ('replace_image','place_brand_asset'):
            asset = owned_asset(self.ws,args['assetId'])
            if asset.kind not in ('image','logo','icon'): raise ValueError('An image, logo or icon is required')
            if name == 'replace_image':
                layer = next(l for l in design['layers'] if l['id']==args['layerId'])
                if layer['type'] != 'image': raise ValueError('Replacement needs an image layer')
                ops = [{'op':'replace_image','layerId':layer['id'],'assetId':asset.id,'source':asset.source}]
            else:
                if asset.source != 'brand_asset': raise ValueError('Placement needs a brand-library asset')
                x0,y0,x1,y1 = args['box']
                if not 0 <= x0 < x1 <= 1 or not 0 <= y0 < y1 <= 1: raise ValueError('Invalid fractional box')
                layer = variants.base(args['role'],x0*design['width'],y0*design['height'],(x1-x0)*design['width'],(y1-y0)*design['height'])
                layer.update(type='image',assetId=asset.id,source=asset.source,fit='contain' if asset.kind=='logo' else 'cover')
                ops = [{'op':'add_layer','layer':layer}]
        elif name == 'edit_generated_image':
            layer = next(l for l in design['layers'] if l['id']==args['layerId'])
            if layer['type'] != 'image' or layer['source'] != 'generated':
                raise PermissionError('Brand assets are locked; choose a generated image layer')
            asset = owned_asset(self.ws,layer['assetId'])
            if asset.source != 'generated': raise PermissionError('The stored asset is not generated')
            if use_stubs():
                asset = storage.save_asset(self.ws, storage.asset_path(asset.id).read_bytes(), 'edited.png','image','generated')
            else:
                asset = edits.edit_generated(self.ws,asset,args['instruction'])
            ops = [{'op':'replace_image','layerId':layer['id'],'assetId':asset.id,'source':'generated'}]
        elif name in ('update_layer','add_text_layer','remove_layer','set_background'):
            ops = edits.to_ops(self.ws,design,self.kit,name,args)
            if name == 'set_background':
                old = design['background']['colorToken']
                ops += [{'op':'update_layer','layerId':l['id'],'props':{'fillToken':args['colorToken']}}
                        for l in design['layers'] if l['type']=='shape' and l['fillToken']==old
                        and (l['role']=='background' or l['w']*l['h']>design['width']*design['height']*.35)]
        else:
            raise ValueError(f'Unknown tool {name}')
        result = self.apply(design,ops)
        key = result['design'].get('label') or result['design']['id']
        if name == 'update_layer' and 'text' in args.get('props',{}):
            note = 'text changed to “' + str(args['props']['text'])[:80] + '”'
        elif name == 'set_background': note = args['colorToken'] + ' background'
        elif name == 'replace_image': note = 'photo swapped for ' + asset.filename[:65]
        elif name == 'edit_generated_image': note = 'generated image updated'
        else: note = name.replace('_',' ')
        self.changes.setdefault(key,[]).append(note)
        return result

    def loop(self):
        self.step('Reviewing your brand, conversation and current designs')
        if any(r.id == 'FONT-FALLBACK' for r in self.kit.rules):
            self.step(FALLBACK_NOTICE)
        request_text = self.text
        if self.attachments and not self.text.strip():
            # A product default, independent of whether the model elects to call the tools.
            source = self.split(self.attachments[0])
            self.options({'sourceDesignId':source['id'],'n':4})
            self.calls = 2
            self.reply_text = 'Created Options A–D from your reference, with editable text, brand colors, fonts and imagery.'
            request_text = 'The reference has already been split and Options A–D have been generated in this turn. Use reply to describe each in one short sentence, under 500 characters total, plain text. Do not generate or edit anything else.'
        if use_stubs():
            self.reply_text = self.reply_text or 'Studio is in stub mode. Attach a reference to create four editable options.'
            return
        context = self.context()
        messages = [{'role':'system','content':SYSTEM}, {'role':'user','content':json.dumps(context)+'\n\nRequest: '+request_text}]
        attached = [storage.asset_path(i) for i in self.attachments]
        for turn in range(MAX_STEPS):
            self.step(f'Considering the next change ({turn+1}/{MAX_STEPS})')
            response = deepseek.retry(deepseek.chat, deepseek.flash(),messages,tools=TOOLS,images=attached or None).choices[0].message
            # The wrapper adds vision to the last user message without mutating messages.
            if attached:
                from app.llm.deepseek import image_messages
                messages = image_messages(messages, attached)
                attached = []
            calls = response.tool_calls or []
            messages.append(response.model_dump(exclude_none=True))
            if not calls:
                self.reply_text = (response.content or '').strip() or self.reply_text
                break
            for call in calls:
                self.calls += 1
                try:
                    if self.calls > MAX_STEPS: raise ValueError('Tool limit reached; summarize completed changes')
                    args = json.loads(call.function.arguments or '{}')
                    result = self.execute(call.function.name,args)
                except (SplitFailedError,BrandSetupError):
                    raise
                except Exception as exc:
                    # Tool failures are recoverable; source guards apply before any model image call.
                    result = {'error':str(exc) if isinstance(exc,(ValueError,PermissionError,KeyError)) else type(exc).__name__}
                    self.step(f"Could not {call.function.name.replace('_',' ')}: {result['error']}")
                messages.append({'role':'tool','tool_call_id':call.id,'content':json.dumps(result)})
            if self.reply_text or self.calls >= MAX_STEPS: break
        # A split-only request must return a visible card even when no later tool edits or generates options.
        if not self.outputs and self.sources:
            source = dict(self.design(next(reversed(self.sources.values()))))
            source.update(label='Reference',version=1)
            self.publish(source)
        if not self.reply_text:
            self.reply_text = self.summary() or 'No designs changed. Please clarify the change you want.'
        self.reply_text = re.sub(r'\*\*|`', '', self.reply_text).strip()
        if len(self.reply_text) > 500:
            self.reply_text = self.summary() or self.reply_text[:497].rsplit(' ',1)[0] + '…'


def run_message(job_id, thread_id, text, attachments, focus):
    thread = db.get('Thread',thread_id)
    session = None
    c.update_job(job_id,status='running',steps=[])
    error = None
    try:
        session = Session(job_id,thread,text,attachments,focus)
        session.loop()
    except Exception as exc:
        log.exception('Studio job %s failed',job_id)
        error = str(exc) if isinstance(exc,(SplitFailedError,BrandSetupError)) else f'Studio could not finish: {type(exc).__name__}'
        if session: session.step(error)
    finally:
        try:
            reply = error or (session.reply_text if session else '') or 'No changes were made.'
            designs = session.outputs_id() if session else []
            steps = list(c.JOBS[job_id].get('steps',[]))
            thread['messages'] += [message('user',text,attachments),message('assistant',reply,designs=designs,steps=steps)]
            db.put('Thread',thread_id,thread['workspaceId'],validate_contract('Thread',thread))
            c.update_job(job_id,reply=reply,status='error' if error else 'done',error=error,progress='Could not finish' if error else 'Done')
        finally:
            with THREAD_LOCK: ACTIVE.discard(thread_id)
