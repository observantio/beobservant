"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

from tests._env import ensure_test_env

ensure_test_env()

from models.grafana.visibility_models import Visibility


def test_visibility_enum_members_and_string_values():
    assert Visibility.PRIVATE == "private"
    assert Visibility.GROUP == "group"
    assert Visibility.TENANT == "tenant"
    assert Visibility.PUBLIC == "public"
    assert [member.value for member in Visibility] == [
        "private",
        "group",
        "tenant",
        "public",
    ]
