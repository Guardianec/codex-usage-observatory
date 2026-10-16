"""Authoritative token arithmetic. No transport or database dependencies."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp required')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timezone required')
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def identifier(value):
    if not isinstance(value, str) or not 0 < len(value) <= 256:
        raise ValueError('invalid identifier')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('control character')
    return value


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError('usage object required')
        keys = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')
        vals = [raw.get(k) for k in keys]
        if any(type(v) is not int or not 0 <= v <= 10**12 for v in vals):
            raise ValueError('invalid token count')
        u = cls(*vals)
        if u.cached_input_tokens > u.input_tokens or u.reasoning_output_tokens > u.output_tokens:
            raise ValueError('invalid subset')
        if type(raw.get('total_tokens')) is not int or raw['total_tokens'] != u.total_tokens:
            raise ValueError('invalid total')
        if raw.get('cache_write_input_tokens', 0) != 0:
            raise ValueError('unverified cache writes')
        return u

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens

    @property
    def uncached_input_tokens(self):
        return self.input_tokens - self.cached_input_tokens

    def metrics(self):
        return {**asdict(self), 'uncached_input_tokens': self.uncached_input_tokens,
                'total_tokens': self.total_tokens}


def cumulative_delta(current, previous):
    """Validation helper only; never produces additional billable response rows."""
    a, b = Usage.parse(current), Usage.parse(previous)
    delta = {k: v - asdict(b)[k] for k, v in asdict(a).items()}
    delta['total_tokens'] = a.total_tokens - b.total_tokens
    return Usage.parse(delta)


def estimate_cost(usage, model, at, prices):
    """Exact model matches; USD API-equivalent estimate, never subscription quota."""
    date = timestamp(at)[:10]
    eligible = [p for p in prices if p['model'] == model and p['effective_date'] <= date]
    if not eligible:
        return None
    p = max(eligible, key=lambda x: x['effective_date'])
    rates = [Decimal(str(p[k])) for k in ('uncached_input_per_million',
              'cached_input_per_million', 'output_per_million')]
    if any(not r.is_finite() or r < 0 for r in rates):
        raise ValueError('invalid price')
    cost = sum(n*r for n, r in zip((usage.uncached_input_tokens,
               usage.cached_input_tokens, usage.output_tokens), rates)) / Decimal(1000000)
    return {'amount': str(cost), 'currency': 'USD', 'basis': 'api-equivalent',
            'effective_date': p['effective_date']}
