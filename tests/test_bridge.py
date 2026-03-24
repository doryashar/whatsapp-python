import pytest
from src.bridge.protocol import (
    encode_request,
    decode_response,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcEvent,
)


def test_encode_request():
    result = encode_request("login", {}, 1)
    assert '"method": "login"' in result
    assert '"id": 1' in result
    assert '"jsonrpc": "2.0"' in result


def test_encode_request_no_params():
    result = encode_request("get_status", request_id=2)
    assert '"method": "get_status"' in result
    assert '"id": 2' in result


def test_decode_response():
    data = '{"jsonrpc":"2.0","result":{"status":"ok"},"id":1}'
    result = decode_response(data)
    assert isinstance(result, JsonRpcResponse)
    assert result.result is not None
    assert result.result["status"] == "ok"
    assert result.id == 1


def test_decode_response_error():
    data = '{"jsonrpc":"2.0","error":{"code":-32000,"message":"Error"},"id":1}'
    result = decode_response(data)
    assert isinstance(result, JsonRpcResponse)
    assert result.error is not None
    assert result.error["code"] == -32000


def test_decode_event():
    data = '{"jsonrpc":"2.0","method":"qr","params":{"qr":"test"}}'
    result = decode_response(data)
    assert isinstance(result, JsonRpcEvent)
    assert result.method == "qr"
    assert result.params["qr"] == "test"


class TestStderrLoopErrorHandling:
    @pytest.mark.asyncio
    async def test_stderr_loop_handles_exception_with_logging(self, caplog):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from src.bridge.client import BaileysBridge

        bridge = BaileysBridge(auth_dir="/tmp/test", auto_login=False)

        bridge._process = MagicMock()
        bridge._process.stderr = AsyncMock()
        bridge._running = True

        bridge._process.stderr.readline = AsyncMock(
            side_effect=RuntimeError("stderr read error")
        )

        with caplog.at_level("WARNING"):
            await bridge._stderr_loop()

        assert any("stderr loop error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_stderr_loop_handles_cancelled_error(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from src.bridge.client import BaileysBridge

        bridge = BaileysBridge(auth_dir="/tmp/test", auto_login=False)

        bridge._process = MagicMock()
        bridge._process.stderr = AsyncMock()
        bridge._running = True

        bridge._process.stderr.readline = AsyncMock(
            side_effect=asyncio.CancelledError()
        )

        await bridge._stderr_loop()

        assert bridge._running is True
