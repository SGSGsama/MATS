"""Small bundled validator for the exact JSON-Schema subset used by contracts.schema.yaml.

It intentionally supports only the keywords present in this Skill's schema. This removes
runtime dependence on jsonschema/rpds while preserving schema-driven validation. Unsupported
schema keywords fail closed during catalog validation instead of being silently ignored.
"""
from __future__ import annotations
import re
from common import Rejected, encode

SUPPORTED = {
    '$schema','$defs','$ref','type','properties','required','additionalProperties','items',
    'minItems','maxItems','uniqueItems','minLength','maxLength','pattern','minimum','maximum',
    'enum','const','oneOf'
}

def _resolve(root, ref):
    if not isinstance(ref,str) or not ref.startswith('#/$defs/'):
        raise Rejected('unsupported schema ref: '+repr(ref))
    key=ref.split('/',3)[-1]
    try:return root['$defs'][key]
    except KeyError as exc: raise Rejected('unknown schema ref: '+ref) from exc

def _type_ok(value, spec):
    names=spec if isinstance(spec,list) else [spec]
    for name in names:
        if name=='null' and value is None:return True
        if name=='object' and isinstance(value,dict):return True
        if name=='array' and isinstance(value,list):return True
        if name=='string' and isinstance(value,str):return True
        if name=='boolean' and type(value) is bool:return True
        if name=='integer' and type(value) is int:return True
        if name=='number' and type(value) in (int,float):return True
    return False

def _json_equal(a,b):
    if type(a) is bool or type(b) is bool: return type(a) is type(b) and a==b
    if type(a) in (int,float) and type(b) in (int,float): return a==b
    return type(a) is type(b) and a==b

def _unique(seq):
    seen=set()
    for item in seq:
        key=encode(item)
        if key in seen:return False
        seen.add(key)
    return True

def _check_keywords(node, path='schema'):
    if isinstance(node,dict):
        bad=set(node)-SUPPORTED
        if bad: raise Rejected(f'unsupported schema keyword at {path}: {sorted(bad)}')
        for k,v in node.items():
            if k in {'properties','$defs'} and isinstance(v,dict):
                for n,s in v.items(): _check_keywords(s,f'{path}/{k}/{n}')
            elif k in {'items'} and isinstance(v,dict): _check_keywords(v,f'{path}/{k}')
            elif k=='oneOf' and isinstance(v,list):
                for i,s in enumerate(v): _check_keywords(s,f'{path}/oneOf/{i}')

def check_catalog(root):
    if not isinstance(root,dict) or '$defs' not in root: raise Rejected('schema catalog missing $defs')
    _check_keywords(root)
    return root

def _validate(root, schema, value, path):
    if '$ref' in schema:
        return _validate(root,_resolve(root,schema['$ref']),value,path)
    if 'oneOf' in schema:
        matches=[];errs=[]
        for branch in schema['oneOf']:
            try:
                _validate(root,branch,value,path);matches.append(branch)
            except Rejected as e: errs.append(str(e))
        if len(matches)!=1:
            detail='; '.join(f'branch {i+1}: {err}' for i,err in enumerate(errs[:4]))
            raise Rejected(f'{path}: oneOf matched {len(matches)} branches' + (f' ({detail})' if detail else ''))
        return
    if 'type' in schema and not _type_ok(value,schema['type']):
        raise Rejected(f'{path}: expected type {schema["type"]!r}')
    if 'const' in schema and not _json_equal(value,schema['const']): raise Rejected(f'{path}: expected constant {schema["const"]!r}')
    if 'enum' in schema and not any(_json_equal(value,x) for x in schema['enum']): raise Rejected(f'{path}: value not in enum')
    if isinstance(value,str):
        if 'minLength' in schema and len(value)<schema['minLength']: raise Rejected(f'{path}: string shorter than minLength')
        if 'maxLength' in schema and len(value)>schema['maxLength']: raise Rejected(f'{path}: string longer than maxLength')
        if 'pattern' in schema and re.search(schema['pattern'],value) is None: raise Rejected(f'{path}: string does not match pattern')
    if type(value) in (int,float):
        if 'minimum' in schema and value<schema['minimum']: raise Rejected(f'{path}: number below minimum')
        if 'maximum' in schema and value>schema['maximum']: raise Rejected(f'{path}: number above maximum')
    if isinstance(value,list):
        if 'minItems' in schema and len(value)<schema['minItems']: raise Rejected(f'{path}: too few items')
        if 'maxItems' in schema and len(value)>schema['maxItems']: raise Rejected(f'{path}: too many items')
        if schema.get('uniqueItems') and not _unique(value): raise Rejected(f'{path}: duplicate array item')
        if 'items' in schema:
            for i,item in enumerate(value): _validate(root,schema['items'],item,f'{path}[{i}]')
    if isinstance(value,dict):
        props=schema.get('properties',{})
        req=set(schema.get('required',[]))
        missing=req-set(value)
        if missing: raise Rejected(f'{path}: missing fields {sorted(missing)}')
        if schema.get('additionalProperties') is False:
            extra=set(value)-set(props)
            if extra: raise Rejected(f'{path}: unexpected fields {sorted(extra)}')
        for key,item in value.items():
            if key in props:_validate(root,props[key],item,f'{path}.{key}')

def validate(root, kind, value):
    check_catalog(root)
    if kind not in root['$defs']: raise Rejected('unknown contract: '+kind)
    _validate(root,root['$defs'][kind],value,kind)
