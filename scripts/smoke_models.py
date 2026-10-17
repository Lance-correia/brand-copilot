#!/usr/bin/env python3
"""Real provider checks, even when USE_STUBS=1. Never print credentials."""
import io
import json
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from PIL import Image
from jsonschema import validate
from app.llm.deepseek import chat
from app.llm import images

output = ROOT / 'data/model-smoke'
output.mkdir(parents=True, exist_ok=True)
checks = []

def check(name, fn):
    try:
        fn()
        print(f'PASS {name}', flush=True)
        checks.append(True)
    except Exception as exc:
        # Key/endpoint validation is explicit; provider exceptions may contain user input.
        message = str(exc) if isinstance(exc, (RuntimeError, AssertionError)) else type(exc).__name__
        print(f'FAIL {name}: {message}', flush=True)
        checks.append(False)

def pro():
    schema = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
    result = chat(os.getenv('DEEPSEEK_PRO_MODEL'), [{'role':'user','content':'Return JSON with ok set to true.'}], json_schema=schema)
    validate(json.loads(result.choices[0].message.content), schema)

def flash():
    tool = {'type':'function','function':{'name':'describe_image','description':'Record the visible image color.','parameters':{'type':'object','properties':{'color':{'type':'string'}},'required':['color'],'additionalProperties':False}}}
    path = output / 'flash-input.png'
    Image.new('RGB',(64,64),'orange').save(path)
    result = chat(os.getenv('DEEPSEEK_FLASH_MODEL'), [{'role':'user','content':'Inspect this image and call describe_image with its dominant color. You must call the tool.'}], tools=[tool], images=[path])
    calls = result.choices[0].message.tool_calls
    assert calls and calls[0].function.name == 'describe_image', 'No describe_image tool call returned'
    validate(json.loads(calls[0].function.arguments), tool['function']['parameters'])

def fast():
    data = images.generate('A warm ceramic cup of coffee in morning light.',1024,1024,os.getenv('IMAGE_MODEL_FAST','gpt-image-2.5-flare'))
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (1024,1024), 'Unexpected generated dimensions'
    (output / 'generated.png').write_bytes(data)

def edit():
    # Fail clearly if fast generation failed; never substitute brand fixture pixels.
    assert (output / 'generated.png').exists(), 'Fast model did not produce this run\'s input image'
    data = images.edit(output / 'generated.png','Make the cup blue.',os.getenv('IMAGE_MODEL_EDIT','gpt-image-2.5-sunburst'))
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    (output / 'edited.png').write_bytes(data)

if __name__ == '__main__':
    (output / 'generated.png').unlink(missing_ok=True)
    check('DeepSeek-V4-Pro schema-valid JSON',pro)
    check('DeepSeek-V4.1-Flash image + tool call',flash)
    check('fast image model 1024x1024',fast)
    check('edit model on generated image',edit)
    sys.exit(0 if all(checks) else 1)
