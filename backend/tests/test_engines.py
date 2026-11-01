"""Engine registry (app/engines.py) and LLM intent routing in the orchestrator."""

import asyncio
import sys
from pathlib import Path

import pytest
from PIL import Image

_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app import orchestrator  # noqa: E402
from app.engines import build_engine  # noqa: E402
from app.models.api import QueryRequest  # noqa: E402


@pytest.fixture(autouse=True)
def fast_mocks(monkeypatch):
    monkeypatch.setenv("MOCK_FAST_MODE", "1")


IMG = Image.new("RGB", (64, 64), (40, 90, 140))


@pytest.mark.parametrize(
    "engine,prefix",
    [("rsunivlm", "rsunivlm_"), ("qwen", "qwen_vl_"), ("hybrid", "qwen_vl_"), ("bogus", "rsunivlm_")],
)
def test_build_engine_mock_tool_prefixes(engine, prefix):
    e = build_engine(engine, "mock")
    assert e.mode == "mock"
    assert e.run_vqa(IMG, "q")["meta"]["tool_used"].startswith(prefix)
    assert e.run_detection(IMG, "Where is the ship?")["meta"]["tool_used"] == prefix + "vg"
    assert e.run_fusion is not None


def test_hybrid_routes_masks_to_rsunivlm():
    e = build_engine("hybrid", "mock")
    assert e.run_detection(IMG, "Highlight the water bodies")["meta"]["tool_used"] == "rsunivlm_seg"
    assert e.run_detection(IMG, "Locate the aircraft")["meta"]["tool_used"] == "qwen_vl_vg"


def _req(query):
    return QueryRequest(images=[{"id": "img1", "url_or_base64": "x", "modality": "optical"}], query=query)


def _engine_with_classifier(fn):
    e = build_engine("qwen", "mock")
    e.mode = "real"  # LLM intent only runs for real engines
    e.classify_intent = fn
    return e


def test_llm_intent_overrides_keyword(monkeypatch):
    monkeypatch.setattr(orchestrator, "ENGINE", _engine_with_classifier(lambda q, m: "captioning"))
    monkeypatch.setattr(orchestrator, "LLM_INTENT_ENABLED", True)
    assert asyncio.run(orchestrator._maybe_llm_intent(_req("What is here?"), "vqa")) == "captioning"


@pytest.mark.parametrize("llm_result", [None, "fusion", "nonsense"])
def test_llm_intent_invalid_keeps_keyword(monkeypatch, llm_result):
    monkeypatch.setattr(orchestrator, "ENGINE", _engine_with_classifier(lambda q, m: llm_result))
    monkeypatch.setattr(orchestrator, "LLM_INTENT_ENABLED", True)
    assert asyncio.run(orchestrator._maybe_llm_intent(_req("What is here?"), "vqa")) == "vqa"


def test_llm_intent_exception_keeps_keyword(monkeypatch):
    def boom(q, m):
        raise RuntimeError("server down")

    monkeypatch.setattr(orchestrator, "ENGINE", _engine_with_classifier(boom))
    monkeypatch.setattr(orchestrator, "LLM_INTENT_ENABLED", True)
    assert asyncio.run(orchestrator._maybe_llm_intent(_req("Find ships"), "detection")) == "detection"


def test_llm_intent_disabled_in_mock_mode(monkeypatch):
    e = build_engine("qwen", "mock")
    e.classify_intent = lambda q, m: "captioning"
    monkeypatch.setattr(orchestrator, "ENGINE", e)
    assert asyncio.run(orchestrator._maybe_llm_intent(_req("What is here?"), "vqa")) == "vqa"


# ── real-mode startup fallback when llama-server is down ──────────────────
def _patch_real_loaders(monkeypatch, reachable):
    from ai_service.fusion.mock import run_fusion
    from ai_service.qwen_vl import mock as qwen_mock
    from ai_service.rsunivlm import mock as rs_mock
    from app import engines

    monkeypatch.setattr(engines, "_load_rsunivlm", lambda mode: rs_mock)
    monkeypatch.setattr(engines, "_load_qwen", lambda mode: qwen_mock)
    monkeypatch.setattr(engines, "_load_fusion", lambda mode: run_fusion)
    monkeypatch.setattr(engines, "_vlm_server_reachable", lambda: (reachable, "http://127.0.0.1:8080"))
    return engines


@pytest.mark.parametrize("requested", ["qwen", "hybrid"])
def test_real_mode_falls_back_to_rsunivlm_when_vlm_down(monkeypatch, requested):
    engines = _patch_real_loaders(monkeypatch, reachable=False)
    e = engines.build_engine(requested, "real")
    assert e.name == "rsunivlm"
    assert any("not reachable" in n for n in e.notes)


def test_real_mode_keeps_hybrid_when_vlm_up(monkeypatch):
    engines = _patch_real_loaders(monkeypatch, reachable=True)
    e = engines.build_engine("hybrid", "real")
    assert e.name == "hybrid" and e.notes == []


def test_default_engine_is_hybrid():
    from app import config
    import os

    if "AI_ENGINE" not in os.environ:
        assert config.AI_ENGINE == "hybrid"
    assert build_engine("", "mock").name == "hybrid"
