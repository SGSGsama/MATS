#!/usr/bin/env python3
"""Measure deterministic prompt-source bytes; provider token usage remains authoritative."""
from __future__ import annotations
import argparse,json
from pathlib import Path

ACTIVATION=('SKILL.md','references/roles/control.md','references/workflow.md','references/routing.md')

def _file(path:Path)->Path:
    value=path/'SKILL.md' if path.is_dir() else path
    if not value.is_file():raise ValueError(f'missing context file: {value}')
    return value

def _sizes(paths):return {str(path):len(path.read_bytes()) for path in paths}

def measure(mats_root:Path,orca_skills=None,orca_full_guide_bytes=0):
    if type(orca_full_guide_bytes) is not int or orca_full_guide_bytes<0:raise ValueError('orca_full_guide_bytes must be a nonnegative integer')
    mats_root=mats_root.resolve();activation=[_file(mats_root/path) for path in ACTIVATION]
    storage=_file(mats_root/'references/storage.md');native=_file(mats_root/'references/native-boundary.md')
    orca={name:_file(Path(path).resolve()) for name,path in (orca_skills or {}).items()}
    activation_sizes=_sizes(activation);orca_sizes={name:len(path.read_bytes()) for name,path in orca.items()}
    core=sum(activation_sizes.values());first_state=core+storage.stat().st_size;orca_total=sum(orca_sizes.values())
    return {'measurement_unit':'utf8_bytes_not_model_tokens','mats_activation':{'files':activation_sizes,'total':core},
            'mats_first_state_additional':storage.stat().st_size,'mats_native_anomaly_additional':native.stat().st_size,
            'orca_skill_entrypoints':{'files':{name:str(path) for name,path in orca.items()},'bytes':orca_sizes,'total':orca_total},
            'orca_full_guide_bytes':orca_full_guide_bytes,
            'normal_after_first_state_with_observed_orca':first_state+orca_total,
            'native_anomaly_with_observed_orca':first_state+native.stat().st_size+orca_total+orca_full_guide_bytes,
            'accounting_rule':'Measure actual Control provider usage; these bytes only attribute loaded sources and must not be added again.'}

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--mats-root',type=Path,required=True);ap.add_argument('--orca-skill',action='append',default=[],metavar='NAME=PATH');ap.add_argument('--orca-full-guide-bytes',type=int,default=0);a=ap.parse_args(argv)
    pairs={}
    for item in a.orca_skill:
        if '=' not in item:ap.error('--orca-skill requires NAME=PATH')
        name,path=item.split('=',1);pairs[name]=Path(path)
    try:print(json.dumps(measure(a.mats_root,pairs,a.orca_full_guide_bytes),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as exc:ap.error(str(exc))

if __name__=='__main__':main()
