"""Copilot chat: Flash tool calls -> validated EditOps. Also the generated-image edit path."""
import json
from app.core import storage
from app.core.validation import validate_contract
from app.llm import deepseek, images
from . import common as c

KEEP = 'Keep the composition. No text, letters, logos or watermarks.'
COMMON = {'x', 'y', 'w', 'h', 'rotation', 'visible', 'locked'}
PROPS = {'text':COMMON | {'text', 'fontToken', 'fontSize', 'colorToken', 'align', 'lineHeight', 'fontWeight'},
         'shape':COMMON | {'fillToken', 'radius', 'shape'}, 'image':COMMON | {'fit'}}
ROLES = ['headline', 'subhead', 'body', 'cta', 'decoration']

def tool(name, description, **props):
    required = [k for k, v in props.items() if not v.pop('optional', False)]
    return {'type':'function', 'function':{'name':name, 'description':description,
            'parameters':{'type':'object', 'properties':props, 'required':required, 'additionalProperties':False}}}

S, N = {'type':'string'}, {'type':'number'}
TOOLS = [
    tool('update_layer', 'Change properties of one layer: text, colorToken, fontToken, fontSize, align, x, y, w, h, '
         'fillToken, radius, visible, rotation.', layerId=dict(S), props={'type':'object'}),
    tool('add_text_layer', 'Add a new text layer on top.', text=dict(S), role={'type':'string', 'enum':ROLES},
         fontToken=dict(S), colorToken=dict(S), x=dict(N), y=dict(N), w=dict(N), h=dict(N),
         fontSize=dict(N, optional=True), align={'type':'string', 'enum':['left', 'center', 'right'], 'optional':True}),
    tool('remove_layer', 'Delete one layer.', layerId=dict(S)),
    tool('replace_image_with_brand_asset', 'Swap an image layer for the brand library image best matching a search query.',
         layerId=dict(S), query=dict(S)),
    tool('edit_generated_image', 'Change the pixels of an AI-generated image layer (source "generated" only) with an instruction.',
         layerId=dict(S), instruction=dict(S)),
    tool('set_background', 'Set the canvas background color token.', colorToken=dict(S)),
]

SYSTEM = (
    'You are the design copilot for a brand-locked layered canvas. Edit the design only by calling tools.\n'
    '- Make the fewest tool calls that do exactly what the user asked; change nothing else.\n'
    '- Text changes use update_layer with props.text. Never use image tools for text.\n'
    '- Colors and fonts must be token names from the brand kit, never hex or family names.\n'
    '- "this", "it" or "selected" means the selected layers.\n'
    '- edit_generated_image works only on image layers whose source is "generated". Brand-asset images are locked; '
    'for those use replace_image_with_brand_asset.\n'
    '- After tool calls, reply with one short sentence. If the request cannot be done on-brand, say why without calling tools.')

def edit_generated(ws, asset, instruction):
    if asset.source != 'generated':
        raise PermissionError('Brand assets are locked')
    data = deepseek.retry(images.edit, storage.asset_path(asset.id), f'{instruction.rstrip(". ")}. {KEEP}')
    return storage.save_asset(ws, data, f'{c.slug(instruction)}.png', 'image', 'generated',
                              {'parentAssetId':asset.id, 'instruction':instruction})

def search_brand_assets(ws, query):
    words = set(query.lower().replace(',', ' ').split())
    score = lambda a: len(words & set(' '.join([a.caption or '', a.filename, *a.tags]).lower().replace('-', ' ').split()))
    candidates = [a for a in storage.list_assets(ws, 'image') if a.source == 'brand_asset']
    return max(candidates, key=score, default=None)

def check_op(design, kit, op):
    """Raise ValueError when an op points at a missing layer, unknown token or forbidden prop."""
    layers = {l['id']:l for l in design['layers']}
    colors, fonts = {col.token for col in kit.colors}, {f.token:f for f in kit.fonts}
    if 'layerId' in op:
        if op['layerId'] not in layers:
            raise ValueError(f"No layer {op['layerId']}")
        if layers[op['layerId']]['locked'] and op['op'] != 'update_layer':
            raise ValueError(f"Layer {op['layerId']} is locked")
    layer = layers.get(op.get('layerId'))
    props = op.get('props') or op.get('layer') or op.get('background') or {}
    if op['op'] == 'update_layer':
        bad = set(props) - PROPS[layer['type']]
        if bad:
            raise ValueError(f"Cannot set {', '.join(sorted(bad))} on a {layer['type']} layer")
        if layer['locked'] and set(props) != {'locked'}:
            raise ValueError(f"Layer {layer['id']} is locked")
    for key in ('colorToken', 'fillToken'):
        if key in props and props[key] not in colors:
            raise ValueError(f'Unknown color token {props[key]}')
    if 'fontToken' in props and props['fontToken'] not in fonts:
        raise ValueError(f"Unknown font token {props['fontToken']}")
    if 'fontSize' in props:
        font = fonts.get(props.get('fontToken') or (layer or {}).get('fontToken'))
        if font:
            props['fontSize'] = min(font.maxSize, max(font.minSize, props['fontSize']))
    validate_contract('EditOp', op)

def to_ops(ws, design, kit, name, args):
    layer = next((l for l in design['layers'] if l['id'] == args.get('layerId')), None)
    if name == 'update_layer':
        return [{'op':'update_layer', 'layerId':args['layerId'], 'props':args.get('props') or {}}]
    if name == 'remove_layer':
        return [{'op':'remove_layer', 'layerId':args['layerId']}]
    if name == 'set_background':
        return [{'op':'set_background', 'background':{'colorToken':args['colorToken']}}]
    if name == 'add_text_layer':
        font = next((f for f in kit.fonts if f.token == args['fontToken']), kit.fonts[-1])
        new = {'id':c.layer_id(), 'type':'text', 'role':args['role'], 'rotation':0, 'visible':True, 'locked':False,
               'x':args['x'], 'y':args['y'], 'w':max(1, args['w']), 'h':max(1, args['h']), 'text':args['text'],
               'fontToken':args['fontToken'], 'colorToken':args['colorToken'], 'align':args.get('align', 'left'),
               'fontSize':args.get('fontSize') or c.fit_font_size(args['text'], args['w'], args['h'], font)}
        return [{'op':'add_layer', 'layer':new}]
    if layer is None or layer['type'] != 'image':
        raise ValueError('That tool needs an image layer')
    if name == 'replace_image_with_brand_asset':
        asset = search_brand_assets(ws, args['query'])
        if not asset:
            raise ValueError('No brand image matches that')
        return [{'op':'replace_image', 'layerId':layer['id'], 'assetId':asset.id, 'source':'brand_asset'}]
    if name == 'edit_generated_image':
        if layer['source'] != 'generated':
            raise ValueError('Brand assets are locked; only generated images can be edited with AI')
        asset = edit_generated(ws, storage.get_asset(layer['assetId']), args['instruction'])
        return [{'op':'replace_image', 'layerId':layer['id'], 'assetId':asset.id, 'source':'generated'}]
    raise ValueError(f'Unknown tool {name}')

def run_chat(ws, design, selection, message):
    kit = storage.get_brand_kit(ws)
    context = {'design':design, 'selection':selection,
               'brandKit':{'colors':[col.model_dump() for col in kit.colors],
                           'fonts':[{'token':f.token, 'minSize':f.minSize, 'maxSize':f.maxSize} for f in kit.fonts]}}
    messages = [{'role':'system', 'content':SYSTEM},
                {'role':'user', 'content':json.dumps(context) + '\n\nRequest: ' + message}]
    reply = deepseek.retry(deepseek.chat, deepseek.flash(), messages, tools=TOOLS).choices[0].message
    ops, notes, working = [], [], design
    for call in reply.tool_calls or []:
        try:
            for op in to_ops(ws, working, kit, call.function.name, json.loads(call.function.arguments or '{}')):
                check_op(working, kit, op)
                working = c.apply_ops(working, [op])  # also validates the resulting design
                ops.append(op)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            notes.append(str(exc).strip("'"))
        except Exception as exc:  # jsonschema errors and failed image edits
            notes.append(f'Skipped {call.function.name}: {type(exc).__name__}')
    text = (reply.content or '').strip() or ('Done.' if ops else 'I could not make that change.')
    return ' '.join([text, *notes]), ops
