import logging
import json
import sys
from typing import Optional
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "tenant"):
            log_data["tenant"] = record.tenant
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type
        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        if hasattr(record, "span_id"):
            log_data["span_id"] = record.span_id

        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "created",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "exc_info",
                "exc_text",
                "thread",
                "threadName",
                "message",
                "tenant",
                "event_type",
                "trace_id",
                "span_id",
            }
        }
        if extra_fields:
            log_data["extra"] = extra_fields

        return json.dumps(log_data, default=str)


_tracer: Optional[trace.Tracer] = None
_logger: Optional[logging.Logger] = None


def setup_telemetry(
    service_name: str = "whatsapp-api",
    service_version: str = "2.0.0",
    otlp_endpoint: Optional[str] = None,
    debug: bool = False,
) -> tuple[trace.Tracer, logging.Logger]:
    global _tracer, _logger

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "service.namespace": "whatsapp",
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    _tracer = trace.get_tracer(service_name, service_version)

    if otlp_endpoint:
        otlp_span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))

    _logger = logging.getLogger("whatsapp")
    _logger.setLevel(logging.DEBUG if debug else logging.INFO)
    _logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    _logger.addHandler(handler)

    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers.clear()
    uvicorn_handler = logging.StreamHandler(sys.stdout)
    uvicorn_handler.setFormatter(JSONFormatter())
    uvicorn_logger.addHandler(uvicorn_handler)

    return _tracer, _logger


def instrument_app(app):
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


def get_logger(name: str = "whatsapp") -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger(name)
        _logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        _logger.addHandler(handler)
    return _logger


def get_tracer(name: str = "whatsapp") -> trace.Tracer:
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(name)
    return _tracer
