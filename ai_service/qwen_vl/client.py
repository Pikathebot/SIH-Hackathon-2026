"""
HTTP client for a locally served vision-language model via an
OpenAI-compatible `/v1/chat/completions` endpoint — by default llama.cpp's
`llama-server` running Qwen3-VL GGUF weights (see scripts/start_vlm_server.ps1).

The same client works unchanged against vLLM, LM Studio or any other
OpenAI-compatible server, so the model can later move to a cloud GPU box by
changing VLM_SERVER_URL only.

Keeping the model in a separate server process (instead of loading weights
into the FastAPI process) means the API restarts instantly, never OOMs the web
worker, and the GPU model can be swapped by restarting the server.

Environment:
  VLM_SERVER_URL   default http://127.0.0.1:8080   (llama-server)
  VLM_MODEL        default qwen3-vl-8b             (alias passed to llama-server)
  VLM_API_KEY      optional bearer token (llama-server --api-key)
  VLM_TIMEOUT_S    default 180
  VLM_MAX_SIDE     default 1280  (longest image side sent to the model, px)
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import httpx
from PIL import Image

from ai_service.common.errors import AIServiceError, MODEL_INFERENCE_FAILED


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class ChatResult:
    text: str
    latency_ms: int
    # Mean per-token probability when the server returns logprobs, else None.
    token_confidence: Optional[float]


def _encode_image(image: Image.Image, max_side: int) -> str:
    """Downscale (aspect preserved) and PNG-encode a PIL image as a data URI."""
    img = image.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _mean_token_prob(choice: dict) -> Optional[float]:
    """OpenAI format: choices[0].logprobs.content = [{token, logprob, ...}, ...]."""
    content = ((choice or {}).get("logprobs") or {}).get("content")
    if not isinstance(content, list) or not content:
        return None
    vals = [t.get("logprob") for t in content if isinstance(t, dict) and isinstance(t.get("logprob"), (int, float))]
    if not vals:
        return None
    return float(sum(math.exp(v) for v in vals) / len(vals))


class VLMClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_s: Optional[float] = None,
        max_side: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or _env("VLM_SERVER_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.model = model or _env("VLM_MODEL", "qwen3-vl-8b")
        self.api_key = api_key if api_key is not None else os.environ.get("VLM_API_KEY")
        self.timeout_s = float(timeout_s or _env("VLM_TIMEOUT_S", "180"))
        self.max_side = int(max_side or _env("VLM_MAX_SIDE", "1280"))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    # ------------------------------------------------------------------ health
    def is_available(self) -> bool:
        """True if the server is up and has finished loading the model."""
        try:
            r = httpx.get(f"{self.base_url}/health", headers=self._headers(), timeout=3.0)
            if r.status_code == 200:
                return True
            # Generic OpenAI-compatible servers may not expose /health
            r = httpx.get(f"{self.base_url}/v1/models", headers=self._headers(), timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    # -------------------------------------------------------------------- chat
    def chat(
        self,
        prompt: str,
        images: Sequence[Image.Image] = (),
        system: Optional[str] = None,
        json_schema: Optional[dict] = None,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> ChatResult:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        if images:
            content: Any = [
                {"type": "image_url", "image_url": {"url": _encode_image(im, self.max_side)}} for im in images
            ] + [{"type": "text", "text": prompt}]
        else:
            content = prompt
        messages.append({"role": "user", "content": content})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "logprobs": True,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": json_schema, "strict": True},
            }

        t0 = time.perf_counter()
        try:
            r = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise AIServiceError(MODEL_INFERENCE_FAILED, "Vision model timed out", detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise AIServiceError(
                MODEL_INFERENCE_FAILED,
                f"Vision model server unreachable at {self.base_url}",
                detail=str(exc),
            ) from exc
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if r.status_code != 200:
            raise AIServiceError(
                MODEL_INFERENCE_FAILED,
                f"Vision model returned HTTP {r.status_code}",
                detail=r.text[:500],
            )
        body = r.json()
        choice = (body.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "") or ""
        return ChatResult(text=text.strip(), latency_ms=latency_ms, token_confidence=_mean_token_prob(choice))

    def chat_json(self, prompt: str, schema: dict, **kwargs) -> tuple[Any, ChatResult]:
        """Chat with a JSON-schema constrained output and parse it."""
        res = self.chat(prompt, json_schema=schema, **kwargs)
        text = res.text
        if text.startswith("```"):  # tolerate fenced output from servers without grammar support
            text = text.strip("`").removeprefix("json").strip()
        try:
            return json.loads(text), res
        except json.JSONDecodeError as exc:
            raise AIServiceError(
                MODEL_INFERENCE_FAILED,
                "Vision model returned malformed JSON",
                detail=res.text[:300],
            ) from exc


_default_client: Optional[VLMClient] = None


def get_client() -> VLMClient:
    global _default_client
    if _default_client is None:
        _default_client = VLMClient()
    return _default_client
