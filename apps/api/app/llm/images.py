"""OpenAI Images API wrappers. Both functions return PNG bytes."""
import base64
import os
from contextlib import ExitStack
from pathlib import Path
from openai import OpenAI
from app.core import config

SUFFIX = 'No text, letters, logos or watermarks.'

def image_prompt(prompt):
    return prompt.rstrip() if prompt.rstrip().endswith(SUFFIX) else prompt.rstrip() + '\n' + SUFFIX

def client():
    if not os.getenv('OPENAI_API_KEY'):
        raise RuntimeError('Set OPENAI_API_KEY in .env')
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=120, max_retries=0)

def decode(result):
    if not result.data or not result.data[0].b64_json:
        raise RuntimeError('Images API returned no base64 image')
    return base64.b64decode(result.data[0].b64_json)

def image_size(w, h, area=1024 * 1024):
    """Size for a w x h slot: about `area` pixels, aspect clamped to 1:3..3:1, both sides divisible by 16."""
    aspect = min(3, max(1 / 3, w / h))
    return round((area * aspect) ** 0.5 / 16) * 16, round((area / aspect) ** 0.5 / 16) * 16

def generate(prompt, width, height, model=None, quality='medium'):
    model = model or os.getenv('IMAGE_MODEL_FAST', 'gpt-image-2.5-flare')
    return decode(client().images.generate(model=model, prompt=image_prompt(prompt), size=f'{width}x{height}',
                                           quality=quality, n=1, output_format='png'))

def edit(image_path, instruction, model=None, mask_path=None):
    # Check known stored inputs as a second guard after the HTTP route's source check.
    path = Path(image_path).resolve()
    if path.is_relative_to((config.DATA_DIR / 'files').resolve()):
        from app.core.storage import get_asset
        asset = get_asset(path.stem)
        if asset.source != 'generated':
            raise PermissionError('Only generated image pixels may go to an image model')
    model = model or os.getenv('IMAGE_MODEL_EDIT', 'gpt-image-2.5-sunburst')
    with ExitStack() as stack:
        args = {'image':stack.enter_context(path.open('rb')), 'model':model,
                'prompt':image_prompt(instruction), 'n':1, 'output_format':'png', 'background':'opaque'}
        if mask_path:
            args['mask'] = stack.enter_context(Path(mask_path).open('rb'))
        return decode(client().images.edit(**args))
