"""
Exercise gatekeeper/start.py path bootstrap under both conditional branches.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path


def test_start_inserts_root_when_not_already_on_sys_path() -> None:
    """Cover the branch where ``_ROOT`` is absent so ``sys.path.remove`` is skipped."""
    gatekeeper_root = str(Path(__file__).resolve().parents[1])
    start_py = Path(gatekeeper_root) / "start.py"
    saved_path = list(sys.path)
    try:
        sys.path[:] = [p for p in sys.path if p != gatekeeper_root]
        sys.modules.pop("start", None)
        spec = importlib.util.spec_from_file_location("start", start_py)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["start"] = module
        spec.loader.exec_module(module)
        assert sys.path[0] == gatekeeper_root
    finally:
        sys.path[:] = saved_path
        sys.modules.pop("start", None)


def test_start_removes_existing_root_before_insert() -> None:
    """Cover the branch where ``_ROOT`` is already present (``sys.path.remove`` runs)."""
    gatekeeper_root = str(Path(__file__).resolve().parents[1])
    saved_path = list(sys.path)
    try:
        sys.modules.pop("start", None)
        sys.path[:] = [p for p in sys.path if p != gatekeeper_root]
        sys.path.insert(0, gatekeeper_root)
        importlib.import_module("start")
        assert sys.path[0] == gatekeeper_root
        assert sys.path.count(gatekeeper_root) == 1
    finally:
        sys.path[:] = saved_path
        sys.modules.pop("start", None)
