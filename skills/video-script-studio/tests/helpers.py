"""Test helpers for loading modules from the hyphenated skill directory."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_script_module(module_name: str) -> ModuleType:
    """Load a module from ``scripts`` without importing the hyphenated package."""
    module_path = SKILL_ROOT / "scripts" / f"{module_name}.py"
    qualified_name = f"video_script_studio_{module_name}"
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module
