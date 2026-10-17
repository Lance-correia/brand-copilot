"""Synchronous OpenAI-compatible DeepSeek chat client. Returns ChatCompletion."""
import base64
import copy
import mimetypes
import os
from pathlib import Path
from openai import OpenAI
from app.core import config  # Loads the repo-root .env before reading model settings.

def chat(model, messages, tools=None, json_schema=None, images=None):
    deployment = str(model or '').strip()
    role = next((role for role in ('PRO', 'FLASH')
                 if deployment and deployment == os.getenv(f'DEEPSEEK_{role}_MODEL', '').strip()), None)
    endpoint_name = f'DEEPSEEK_{role}_ENDPOINT' if role else 'AZURE_DEEPSEEK_ENDPOINT'
    key_name = f'DEEPSEEK_{role}_API_KEY' if role else 'AZURE_DEEPSEEK_API_KEY'
    endpoint = os.getenv(endpoint_name, '').strip() or os.getenv('AZURE_DEEPSEEK_ENDPOINT', '').strip()
    key = os.getenv(key_name, '').strip() or os.getenv('AZURE_DEEPSEEK_API_KEY', '').strip()
    if not endpoint or not key or not model:
        raise RuntimeError(f'Set {endpoint_name}, {key_name} and the deployment name in .env')
    payload = copy.deepcopy(messages)
    if images:
        content = []
        if payload and payload[-1].get('role') == 'user':
            last = payload.pop()['content']
            content = [{'type':'text','text':last}] if isinstance(last, str) else last
        for image in images:
            if isinstance(image, str) and image.startswith(('data:', 'https://', 'http://')):
                url = image
            else:
                path = Path(image)
                mime = mimetypes.guess_type(path.name)[0] or 'image/png'
                url = f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()
            content.append({'type':'image_url', 'image_url':{'url':url}})
        payload.append({'role':'user','content':content})
    options = {}
    if tools:
        options['tools'] = tools
    if json_schema:
        options['response_format'] = {'type':'json_schema', 'json_schema':{'name':'result','strict':True,'schema':json_schema}}
    client = OpenAI(base_url=endpoint.rstrip('/'), api_key=key, timeout=90, max_retries=0)
    return client.chat.completions.create(model=deployment, messages=payload, **options)
