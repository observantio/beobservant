"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""
from typing import Tuple, Optional
from config import config as app_config


def _cap_pagination(limit: Optional[int], offset: int) -> Tuple[int, int]:
    capped_limit = max(1, min(int(limit) if limit is not None else int(app_config.DEFAULT_QUERY_LIMIT), int(app_config.MAX_QUERY_LIMIT)))
    return capped_limit, max(0, int(offset))
