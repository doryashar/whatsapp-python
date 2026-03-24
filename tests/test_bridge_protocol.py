import json
import pytest

from src.bridge.protocol import (
    encode_request,
    decode_response,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcEvent,
)


class TestEncodeRequest:
    def test_basic_request(self):
        result = encode_request("login", {"auto_login": True}, 1)
        data = json.loads(result)
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "login"
        assert data["params"] == {"auto_login": True}
        assert data["id"] == 1

    def test_request_with_dict_params(self):
        result = encode_request("send_message", {"to": "123", "text": "hi"}, 3)
        data = json.loads(result)
        assert data["params"]["to"] == "123"
        assert data["params"]["text"] == "hi"

    def test_request_without_params(self):
        result = encode_request("get_status", None, 2)
        data = json.loads(result)
        assert "params" not in data

    def test_request_without_params_no_id(self):
        result = encode_request("get_status")
        data = json.loads(result)
        assert "params" not in data
        assert "id" not in data

    def test_request_without_id(self):
        result = encode_request("ping", {"data": "test"})
        data = json.loads(result)
        assert "id" not in data
        assert data["method"] == "ping"

    def test_request_with_zero_id(self):
        result = encode_request("method", {}, 0)
        data = json.loads(result)
        assert data["id"] == 0

    def test_request_with_empty_params(self):
        result = encode_request("method", {}, 1)
        data = json.loads(result)
        assert data["params"] == {}

    def test_request_returns_valid_json(self):
        result = encode_request("test", {"key": "value"}, 1)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_request_with_nested_params(self):
        params = {"outer": {"inner": [1, 2, 3]}}
        result = encode_request("test", params, 1)
        data = json.loads(result)
        assert data["params"]["outer"]["inner"] == [1, 2, 3]

    def test_request_with_special_characters(self):
        params = {"text": "hello \u00e9 world \u00f1"}
        result = encode_request("send_message", params, 1)
        data = json.loads(result)
        assert data["params"]["text"] == "hello \u00e9 world \u00f1"


class TestDecodeResponse:
    def test_success_response(self):
        raw = json.dumps({"jsonrpc": "2.0", "result": {"status": "ok"}, "id": 1})
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.result == {"status": "ok"}
        assert msg.id == 1
        assert msg.error is None

    def test_error_response(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": "Server error"},
                "id": 1,
            }
        )
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.error is not None
        assert msg.error["code"] == -32000
        assert msg.error["message"] == "Server error"
        assert msg.result is None

    def test_event_notification(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "message",
                "params": {"text": "hello"},
            }
        )
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcEvent)
        assert msg.method == "message"
        assert msg.params == {"text": "hello"}

    def test_non_json_rpc_returns_none(self):
        raw = json.dumps({"type": "not_jsonrpc"})
        msg = decode_response(raw)
        assert msg is None

    def test_malformed_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            decode_response("not json at all")

    def test_response_with_both_result_and_error(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "result": {"data": "val"},
                "error": {"code": 1, "message": "err"},
                "id": 5,
            }
        )
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.result == {"data": "val"}
        assert msg.error == {"code": 1, "message": "err"}

    def test_event_with_empty_params(self):
        raw = json.dumps({"jsonrpc": "2.0", "method": "ping", "params": {}})
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcEvent)
        assert msg.method == "ping"
        assert msg.params == {}

    def test_response_with_null_result(self):
        raw = json.dumps({"jsonrpc": "2.0", "result": None, "id": 1})
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.result is None

    def test_response_with_empty_string_jsonrpc(self):
        raw = json.dumps({"jsonrpc": "", "method": "test"})
        msg = decode_response(raw)
        assert msg is None

    def test_response_with_id_zero(self):
        raw = json.dumps({"jsonrpc": "2.0", "result": "ok", "id": 0})
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.id == 0

    def test_event_with_nested_params(self):
        params = {"contacts": [{"jid": "a@b.c", "name": "test"}]}
        raw = json.dumps({"jsonrpc": "2.0", "method": "contacts", "params": params})
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcEvent)
        assert len(msg.params["contacts"]) == 1

    def test_qr_event(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "qr",
                "params": {"qr": "data:image/png;base64,abc"},
            }
        )
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcEvent)
        assert msg.method == "qr"

    def test_disconnected_event(self):
        raw = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "disconnected",
                "params": {"reason": "logout", "reason_name": "loggedOut"},
            }
        )
        msg = decode_response(raw)
        assert isinstance(msg, JsonRpcEvent)
        assert msg.params["reason_name"] == "loggedOut"
