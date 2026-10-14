"""Small tracing SDK inspired by OTel span/context concepts, not an OTLP implementation."""
import inspect
import re
import time
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

from .storage import now

_current = ContextVar("evalforge_current_span", default=None)
_sensitive = re.compile(r"api.?key|authorization|password|secret|access.?token", re.I)


def redact(value, key=""):
    if _sensitive.search(str(key)):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value[:100]]
    if isinstance(value, str):
        value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]+", "Bearer [REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
        value = re.sub(r"\b1[3-9]\d{9}\b", "[PHONE]", value)
        return value[:18000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return repr(value)[:1000]


class Recorder:
    def __init__(self, db):
        self.db = db

    def annotate(self, **attributes):
        span = _current.get()
        if span is not None:
            span["attributes"].update(redact(attributes))

    def current_ids(self):
        span = _current.get()
        return {k: span[k] for k in ("trace_id", "span_id")} if span else {}

    def trace(self, name, kind="tool"):
        def decorator(fn):
            def begin(args, kwargs):
                parent = _current.get()
                try:
                    inputs = dict(inspect.signature(fn).bind(*args, **kwargs).arguments)
                    inputs.pop("self", None)
                except TypeError:
                    inputs = {"args": args, "kwargs": kwargs}
                span = {
                    "span_id": uuid4().hex[:16], "trace_id": parent["trace_id"] if parent else uuid4().hex,
                    "parent_span_id": parent["span_id"] if parent else None,
                    "name": name, "kind": kind, "started_at": now(), "status": "ok",
                    "input": redact(inputs), "output": None, "attributes": {}, "error": None,
                }
                return span, _current.set(span), time.perf_counter()

            def finish(span, token, started):
                span["duration_ms"] = round((time.perf_counter() - started) * 1000, 4)
                span["ended_at"] = now()
                _current.reset(token)
                # Fail visibly if persistence fails; never silently lose an audit record.
                self.db.save_span(span)

            if inspect.iscoroutinefunction(fn):
                @wraps(fn)
                async def asynchronous(*args, **kwargs):
                    span, token, started = begin(args, kwargs)
                    try:
                        result = await fn(*args, **kwargs)
                        span["output"] = redact(result)
                        return result
                    except BaseException as exc:
                        span.update(status="error", error=redact(f"{type(exc).__name__}: {exc}"))
                        raise
                    finally:
                        finish(span, token, started)
                return asynchronous

            @wraps(fn)
            def synchronous(*args, **kwargs):
                span, token, started = begin(args, kwargs)
                try:
                    result = fn(*args, **kwargs)
                    span["output"] = redact(result)
                    return result
                except BaseException as exc:
                    span.update(status="error", error=redact(f"{type(exc).__name__}: {exc}"))
                    raise
                finally:
                    finish(span, token, started)
            return synchronous
        return decorator
