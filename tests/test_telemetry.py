import json
import logging
import pytest
from unittest.mock import patch, MagicMock
from src.telemetry import (
    JSONFormatter,
    setup_telemetry,
    instrument_app,
    get_logger,
    get_tracer,
)


class TestJSONFormatter:
    def test_basic_format(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        data = json.loads(result)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["logger"] == "test"
        assert data["module"] == "test"
        assert data["function"] is None
        assert "timestamp" in data

    def test_format_with_exception(self):
        fmt = JSONFormatter()
        import sys

        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=None,
            exc_info=exc_info,
        )
        result = fmt.format(record)
        data = json.loads(result)
        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_format_with_tenant_extra(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="tenant event",
            args=None,
            exc_info=None,
        )
        record.tenant = "TestTenant"
        result = fmt.format(record)
        data = json.loads(result)
        assert data["tenant"] == "TestTenant"

    def test_format_with_event_type_extra(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="event happened",
            args=None,
            exc_info=None,
        )
        record.event_type = "message"
        result = fmt.format(record)
        data = json.loads(result)
        assert data["event_type"] == "message"

    def test_format_with_trace_id(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="traced",
            args=None,
            exc_info=None,
        )
        record.trace_id = "abc123"
        record.span_id = "def456"
        result = fmt.format(record)
        data = json.loads(result)
        assert data["trace_id"] == "abc123"
        assert data["span_id"] == "def456"

    def test_format_with_custom_extra(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="extra data",
            args=None,
            exc_info=None,
        )
        record.custom_field = "custom_value"
        result = fmt.format(record)
        data = json.loads(result)
        assert "extra" in data
        assert data["extra"]["custom_field"] == "custom_value"

    def test_format_output_is_valid_json(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="json test",
            args=None,
            exc_info=None,
        )
        result = fmt.format(record)
        json.loads(result)  # Should not raise

    def test_format_with_args(self):
        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("World",),
            exc_info=None,
        )
        result = fmt.format(record)
        data = json.loads(result)
        assert data["message"] == "Hello World"


class TestSetupTelemetry:
    def test_returns_tracer_and_logger(self):
        tracer, logger = setup_telemetry(debug=True)
        assert tracer is not None
        assert logger is not None
        assert logger.name == "whatsapp"
        assert logger.level == logging.DEBUG

    def test_info_level_when_not_debug(self):
        tracer, logger = setup_telemetry(debug=False)
        assert logger.level == logging.INFO

    def test_custom_service_name(self):
        tracer, logger = setup_telemetry(service_name="custom", debug=True)
        assert logger is not None

    def test_custom_service_version(self):
        tracer, logger = setup_telemetry(service_version="3.0.0", debug=True)
        assert logger is not None

    def test_without_otlp_endpoint(self):
        tracer, logger = setup_telemetry(otlp_endpoint=None, debug=True)
        assert tracer is not None

    @patch("src.telemetry.OTLPSpanExporter")
    def test_with_otlp_endpoint(self, mock_exporter):
        tracer, logger = setup_telemetry(
            otlp_endpoint="http://localhost:4317", debug=True
        )
        assert tracer is not None

    def test_clears_existing_handlers(self):
        from src.telemetry import _logger

        original_handlers = _logger.handlers.copy() if _logger else []
        tracer, logger = setup_telemetry(debug=True)
        assert len(logger.handlers) >= 1
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)


class TestInstrumentApp:
    @patch("src.telemetry.FastAPIInstrumentor")
    @patch("src.telemetry.HTTPXClientInstrumentor")
    def test_instruments_app(self, mock_httpx, mock_fastapi):
        app = MagicMock()
        instrument_app(app)
        mock_fastapi.instrument_app.assert_called_once_with(app)
        mock_httpx.return_value.instrument.assert_called_once()


class TestGetLogger:
    def test_default_logger(self):
        logger = get_logger()
        assert logger.name == "whatsapp"

    def test_custom_name_logger(self):
        logger = get_logger("custom.name")
        assert logger.name == "custom.name"

    def test_returns_logger_instance(self):
        logger = get_logger()
        assert isinstance(logger, logging.Logger)


class TestGetTracer:
    def test_returns_tracer(self):
        tracer = get_tracer()
        assert tracer is not None

    def test_custom_name(self):
        tracer = get_tracer("custom")
        assert tracer is not None
