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
    assert '"method":"login"' in result
    assert '"id":1' in result
    assert '"jsonrpc":"2.0"' in result


def test_encode_request_no_params():
    result = encode_request("get_status", request_id=2)
    assert '"method":"get_status"' in result
    assert '"id":2' in result


def test_decode_response():
    data = '{"jsonrpc":"2.0","result":{"status":"ok"},"id":1}'
    result = decode_response(data)
    assert isinstance(result, JsonRpcResponse)
    assert result.result["status"] == "ok"
    assert result.id == 1


def test_decode_response_error():
    data = '{"jsonrpc":"2.0","error":{"code":-32000,"message":"Error"},"id":1}'
    result = decode_response(data)
    assert isinstance(result, JsonRpcResponse)
    assert result.error["code"] == -32000


def test_decode_event():
    data = '{"jsonrpc":"2.0","method":"qr","params":{"qr":"test"}}'
    result = decode_response(data)
    assert isinstance(result, JsonRpcEvent)
    assert result.method == "qr"
    assert result.params["qr"] == "test"
