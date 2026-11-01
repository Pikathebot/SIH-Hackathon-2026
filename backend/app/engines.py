"""
AI engine registry — decides which implementation backs each contract function.

Two orthogonal switches (env vars, see config.py):
  AI_ENGINE        rsunivlm | qwen | hybrid     which model family
  AI_SERVICE_MODE  mock | real                  contract mock vs real inference

  rsunivlm  all RS tasks via RSUniVLM (original behaviour)
  qwen      VQA / captioning / grounding / change text via Qwen-VL (llama-server);
            mask-mode detection via spectral extractors or rasterised boxes
  hybrid    (the default) Qwen-VL for VQA, captioning, bbox grounding and change
            text; RSUniVLM [SEG] for mask-mode detection when its weights are
            importable, otherwise falls back to the Qwen engine's mask path.
            Chosen by side-by-side evaluation on sample_data (2026-11-01).

In real mode, qwen/hybrid need llama-server to be reachable when the engine is
built; if it is not, the engine falls back to rsunivlm and records why in
`Engine.notes` (surfaced by /health) instead of failing every request.

Fusion (optical+SAR) always uses ai_service/fusion regardless of engine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

VALID_ENGINES = ("rsunivlm", "qwen", "hybrid")


@dataclass
class Engine:
    name: str
    mode: str
    run_vqa: Callable
    run_captioning: Callable
    run_detection: Callable
    run_change_detection: Callable
    run_fusion: Callable
    # Optional LLM intent classifier: (query, modalities) -> task | None
    classify_intent: Optional[Callable] = None
    notes: list[str] = field(default_factory=list)


def _load_rsunivlm(mode: str):
    if mode == "real":
        from ai_service.rsunivlm import wrapper as m
    else:
        from ai_service.rsunivlm import mock as m
    return m


def _load_qwen(mode: str):
    if mode == "real":
        from ai_service.qwen_vl import wrapper as m
    else:
        from ai_service.qwen_vl import mock as m
    return m


def _load_fusion(mode: str):
    if mode == "real":
        from ai_service.fusion.wrapper import run_fusion
    else:
        from ai_service.fusion.mock import run_fusion
    return run_fusion


def _hybrid_detection(qwen_mod, rs_mod):
    from ai_service.rsunivlm.parsing import resolve_detection_mode

    def run_detection(image, query, mode="auto"):
        resolved = resolve_detection_mode(query, mode=mode)
        if resolved == "mask" and rs_mod is not None:
            return rs_mod.run_detection(image, query, mode="mask")
        return qwen_mod.run_detection(image, query, mode=resolved)

    return run_detection


def _vlm_server_reachable() -> tuple[bool, str]:
    try:
        from ai_service.qwen_vl.client import get_client

        c = get_client()
        return c.is_available(), c.base_url
    except Exception as exc:
        return False, str(exc)


def build_engine(engine_name: str, mode: str) -> Engine:
    engine_name = (engine_name or "hybrid").lower()
    if engine_name not in VALID_ENGINES:
        logger.warning("Unknown AI_ENGINE=%r, falling back to 'rsunivlm'", engine_name)
        engine_name = "rsunivlm"
    mode = "real" if mode == "real" else "mock"
    run_fusion = _load_fusion(mode)

    notes: list[str] = []
    if engine_name in ("qwen", "hybrid") and mode == "real":
        ok, where = _vlm_server_reachable()
        if not ok:
            notes.append(
                f"AI_ENGINE={engine_name} requested but the VLM server ({where}) is not reachable; "
                "using rsunivlm. Start it with scripts/start_vlm_server.ps1 and restart the backend."
            )
            logger.warning(notes[-1])
            engine_name = "rsunivlm"

    if engine_name == "rsunivlm":
        m = _load_rsunivlm(mode)
        return Engine(engine_name, mode, m.run_vqa, m.run_captioning, m.run_detection,
                      m.run_change_detection, run_fusion, notes=notes)

    q = _load_qwen(mode)
    if engine_name == "qwen":
        return Engine(engine_name, mode, q.run_vqa, q.run_captioning, q.run_detection,
                      q.run_change_detection, run_fusion, classify_intent=q.classify_intent)

    # hybrid
    try:
        rs = _load_rsunivlm(mode)
    except Exception as exc:  # torch / weights missing → degrade gracefully
        rs = None
        notes.append(f"RSUniVLM unavailable for [SEG] ({exc}); using Qwen mask path")
        logger.warning(notes[-1])
    return Engine(engine_name, mode, q.run_vqa, q.run_captioning, _hybrid_detection(q, rs),
                  q.run_change_detection, run_fusion, classify_intent=q.classify_intent, notes=notes)


def engine_health(engine: Engine) -> dict:
    """Best-effort reachability info for /health."""
    info: dict = {"engine": engine.name, "mode": engine.mode, "notes": engine.notes}
    if engine.name in ("qwen", "hybrid") and engine.mode == "real":
        try:
            from ai_service.qwen_vl.client import get_client

            c = get_client()
            info["vlm_server"] = c.base_url
            info["vlm_model"] = c.model
            info["vlm_available"] = c.is_available()
        except Exception as exc:
            info["vlm_available"] = False
            info["vlm_error"] = str(exc)
    return info
