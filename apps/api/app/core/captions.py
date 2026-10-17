"""Background captioning: raster images go to DeepSeek-V4.1-Flash; fonts, PDFs and SVGs get a local caption."""
import json
import logging
import os
import re
from pathlib import Path
from . import storage
from .config import use_stubs

log = logging.getLogger(__name__)
SCHEMA = {'type': 'object', 'properties': {'caption': {'type': 'string'}, 'tags': {'type': 'array', 'items': {'type': 'string'}}},
          'required': ['caption', 'tags'], 'additionalProperties': False}
PROMPT = ('Describe this brand {kind} for a design asset library. Return JSON: caption is one short sentence '
          '(what it shows, colors, mood); tags are 3-8 lowercase single words.')

def local_caption(asset):
    if asset.kind == 'font':
        return f"{asset.meta.get('family', Path(asset.filename).stem)} {asset.meta.get('weight', '')}".strip(), ['font']
    words = [w for w in re.split(r'[\W_]+', Path(asset.filename).stem.lower()) if w and not w.isdigit()]
    return ' '.join(words).capitalize() or asset.kind, list(dict.fromkeys([asset.kind, *words]))

def parse_json(text):
    return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip()))

def caption_asset(asset_id, use_model=None):
    """Fill caption and tags. Never raises: a background task has nobody to report to."""
    try:
        asset = storage.get_asset(asset_id)
        caption, tags = local_caption(asset)
        raster = asset.mime.startswith('image/') and asset.mime != 'image/svg+xml'
        if raster and (not use_stubs() if use_model is None else use_model):
            try:
                from app.llm.deepseek import chat
                result = chat(os.getenv('DEEPSEEK_FLASH_MODEL'), [{'role': 'user', 'content': PROMPT.format(kind=asset.kind)}],
                              json_schema=SCHEMA, images=[storage.asset_path(asset_id)])
                data = parse_json(result.choices[0].message.content)
                caption, tags = str(data['caption']).strip(), [str(t).strip().lower() for t in data['tags'] if str(t).strip()]
            except Exception:
                log.exception('Model captioning failed for %s; using filename caption', asset_id)
        storage.set_caption(asset_id, caption, tags)
    except Exception:
        log.exception('Captioning failed for %s', asset_id)
