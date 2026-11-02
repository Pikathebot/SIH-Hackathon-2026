"""
Every ai_service / backend module must import cleanly.

Mock mode never imports the real engine wrappers, so a broken import there (e.g. a removed
re-export) would otherwise only surface when someone starts the GPU stack. Modules whose
heavy dependencies (torch, transformers) are not installed — the slim CI image — are skipped.
"""

import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_HEAVY = {"torch", "torchvision", "transformers", "peft", "accelerate", "timm", "open_clip", "einops", "av"}


def _modules():
    for pkg, base in (("ai_service", ROOT / "ai_service"), ("app", ROOT / "backend" / "app")):
        for info in pkgutil.walk_packages([str(base)], prefix=f"{pkg}."):
            if ".vendor" in info.name or ".tests" in info.name or info.name.endswith(("test_contract_conformance", "conftest")):
                continue
            yield info.name


@pytest.mark.parametrize("name", sorted(set(_modules())))
def test_module_imports(name):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] in _HEAVY:
            pytest.skip(f"{name} needs {exc.name} (GPU requirements)")
        raise
