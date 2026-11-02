"""VLMClient request/response handling against a stubbed OpenAI-compatible server."""

import json
import math

import httpx
import pytest
from PIL import Image

from ai_service.common.errors import AIServiceError, MODEL_INFERENCE_FAILED
from ai_service.qwen_vl import client as client_mod
from ai_service.qwen_vl.client import VLMClient


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _completion(content, logprobs=None):
    choice = {"message": {"role": "assistant", "content": content}}
    if logprobs is not None:
        choice["logprobs"] = {"content": [{"token": "t", "logprob": lp} for lp in logprobs]}
    return {"choices": [choice]}


@pytest.fixture
def captured(monkeypatch):
    box = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        box.update(url=url, payload=json, headers=headers)
        return box.get("response", _Resp(200, _completion("hello", [math.log(0.9), math.log(0.7)])))

    monkeypatch.setattr(client_mod.httpx, "post", fake_post)
    return box


def test_payload_shape_with_images_and_schema(captured):
    c = VLMClient(base_url="http://vlm:8080/", model="m", api_key="k")
    res = c.chat("describe", images=[Image.new("RGB", (4000, 2000))], system="sys", json_schema={"type": "object"})
    p = captured["payload"]
    assert captured["url"] == "http://vlm:8080/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer k"}
    assert p["model"] == "m" and p["logprobs"] is True
    assert p["messages"][0] == {"role": "system", "content": "sys"}
    parts = p["messages"][1]["content"]
    assert parts[0]["type"] == "image_url" and parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert parts[-1] == {"type": "text", "text": "describe"}
    assert p["response_format"]["type"] == "json_schema"
    assert res.text == "hello"
    assert res.token_confidence == pytest.approx(0.8)


def test_image_downscaled_to_max_side():
    import base64
    import io
    uri = client_mod._encode_image(Image.new("RGB", (4000, 2000)), 1000)
    img = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
    assert img.size == (1000, 500)


def test_no_logprobs_gives_none(captured):
    captured["response"] = _Resp(200, _completion("x"))
    assert VLMClient().chat("q").token_confidence is None


def test_http_error_raises_contract_error(captured):
    captured["response"] = _Resp(500, {"error": "boom"})
    with pytest.raises(AIServiceError) as e:
        VLMClient().chat("q")
    assert e.value.code == MODEL_INFERENCE_FAILED


def test_unreachable_raises_contract_error(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(client_mod.httpx, "post", boom)
    with pytest.raises(AIServiceError) as e:
        VLMClient().chat("q")
    assert e.value.code == MODEL_INFERENCE_FAILED


def test_chat_json_tolerates_code_fence(captured):
    captured["response"] = _Resp(200, _completion('```json\n{"task": "vqa"}\n```'))
    data, _ = VLMClient().chat_json("q", {"type": "object"})
    assert data == {"task": "vqa"}


def test_chat_json_malformed_raises(captured):
    captured["response"] = _Resp(200, _completion("not json"))
    with pytest.raises(AIServiceError):
        VLMClient().chat_json("q", {"type": "object"})
