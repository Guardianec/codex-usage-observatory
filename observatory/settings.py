"""Explicit local preferences; never writes to Codex's own directory."""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from .domain import identifier

DEFAULTS={'threshold_tokens':5000000,'threshold_requests':100,'threshold_minutes':60,'threshold_multiple':3,'prices':[]}


def validate(raw):
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS):raise ValueError('invalid settings')
    value={**DEFAULTS,**raw}
    for k in ('threshold_tokens','threshold_requests','threshold_minutes','threshold_multiple'):
        if type(value[k]) not in (int,float) or not 0<value[k]<=10**12:raise ValueError('invalid threshold')
    if not isinstance(value['prices'],list) or len(value['prices'])>200:raise ValueError('invalid rates')
    seen=set()
    for p in value['prices']:
        if not isinstance(p,dict) or set(p)!={'model','effective_date','uncached_input_per_million','cached_input_per_million','output_per_million'}:raise ValueError('invalid price entry')
        identifier(p['model']);date.fromisoformat(p['effective_date'])
        key=(p['model'],p['effective_date'])
        if key in seen:raise ValueError('duplicate price')
        seen.add(key)
        for k in ('uncached_input_per_million','cached_input_per_million','output_per_million'):
            try:n=Decimal(str(p[k]))
            except InvalidOperation:raise ValueError('invalid rate') from None
            if not n.is_finite() or not 0<=n<=100000:raise ValueError('invalid rate')
    return value


def load(path):
    if not Path(path).exists():return {**DEFAULTS,'prices':[]}
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def save(path,raw):
    value=validate(raw);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8');temp.replace(path)
    return value
