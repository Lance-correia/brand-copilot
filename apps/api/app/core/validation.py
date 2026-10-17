import json
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from pydantic import BaseModel
from .config import ROOT

@lru_cache
def validators():
    schemas = [json.loads(p.read_text()) for p in (ROOT / 'packages/schema').glob('*.schema.json')]
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)
    return {s['title']: Draft202012Validator(s, registry=registry, format_checker=FormatChecker()) for s in schemas}

def validate_contract(name, value):
    data = value.model_dump(mode='json', exclude_unset=True) if isinstance(value, BaseModel) else value
    validators()[name].validate(data)
    return data
