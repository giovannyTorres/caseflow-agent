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

def setup():
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
