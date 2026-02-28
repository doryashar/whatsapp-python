import json
from typing import Any, Optional
from pydantic import BaseModel


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[dict[str, Any]] = None
    id: Optional[int] = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict[str, Any]] = None
    id: Optional[int] = None


class JsonRpcEvent(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any]


def encode_request(
    method: str, params: Optional[dict] = None, request_id: Optional[int] = None
) -> str:
    req = JsonRpcRequest(jsonrpc="2.0", method=method, params=params, id=request_id)
    return json.dumps(req.model_dump(exclude_none=True))


def decode_response(data: str) -> JsonRpcResponse | JsonRpcEvent:
    parsed = json.loads(data)
    if "id" in parsed and ("result" in parsed or "error" in parsed):
        return JsonRpcResponse(**parsed)
    return JsonRpcEvent(**parsed)
