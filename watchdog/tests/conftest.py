"""
Copyright (c) 2026 Stefan Kumarasinghe.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0
"""

import os
import sys
from typing import Any

import pytest
import sqlalchemy
from sqlalchemy.engine import Engine

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT in sys.path:
    sys.path.remove(ROOT)
sys.path.insert(0, ROOT)

_ORIGINAL_CREATE_ENGINE = sqlalchemy.create_engine
_TRACKED_ENGINES: list[Engine] = []


def _tracking_create_engine(*args: Any, **kwargs: Any) -> Engine:
    engine = _ORIGINAL_CREATE_ENGINE(*args, **kwargs)
    _TRACKED_ENGINES.append(engine)
    return engine


sqlalchemy.create_engine = _tracking_create_engine


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    while _TRACKED_ENGINES:
        engine = _TRACKED_ENGINES.pop()
        try:
            engine.dispose()
        except Exception:
            continue
