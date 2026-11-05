import json
import logging
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({'level': record.levelname, 'event': record.getMessage(),
                           'correlation_id': getattr(record, 'correlation_id', None),
                           'trace_id': format(trace.get_current_span().get_span_context().trace_id, '032x')})

def sanitize_http_span(span, scope):
    if not span.is_recording():
        return
    # Do not export query strings. Secret-like values can be supplied to any route,
    # including /health, before business validation ever runs.
    path = scope.get('path', '/').split('?', 1)[0]
    host, port = scope.get('server') or ('localhost', 80)
    safe_url = f"{scope.get('scheme', 'http')}://{host}:{port}{path}"
    for key, value in [('http.url', safe_url), ('url.full', safe_url), ('http.target', path), ('url.query', '')]:
        span.set_attribute(key, value)


def setup():
    # Uvicorn's default access format includes the raw query; retain our bounded
    # structured method/status/correlation log instead, across every entrypoint.
    logging.getLogger('uvicorn.access').disabled = True
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    if not logging.getLogger('caseflow').handlers:
        logging.getLogger('caseflow').addHandler(handler)
    logging.getLogger('caseflow').setLevel(logging.INFO)
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        if os.getenv("OTEL_CONSOLE", "false") == "true":
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
