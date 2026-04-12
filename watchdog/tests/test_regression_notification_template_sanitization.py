"""
Regression tests for HTML template rendering and sanitization rules.
"""

from __future__ import annotations

try:
    from ._env import ensure_test_env
except ImportError:
    from tests._env import ensure_test_env

ensure_test_env()

from services import notification_service as notification_mod


def test_render_html_template_returns_none_for_missing_template(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(notification_mod, "_EMAIL_TEMPLATE_ROOT", tmp_path)

    rendered = notification_mod._render_html_template("missing.html", {"name": "Alice"})

    assert rendered is None


def test_render_html_template_escapes_standard_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(notification_mod, "_EMAIL_TEMPLATE_ROOT", tmp_path)
    template = tmp_path / "welcome.html"
    template.write_text("Hello ${name}", encoding="utf-8")

    rendered = notification_mod._render_html_template("welcome.html", {"name": "<b>Alice</b>"})

    assert rendered == "Hello &lt;b&gt;Alice&lt;/b&gt;"


def test_render_html_template_allows_raw_html_for_html_suffix_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(notification_mod, "_EMAIL_TEMPLATE_ROOT", tmp_path)
    template = tmp_path / "welcome.html"
    template.write_text("${login_row_html}", encoding="utf-8")

    rendered = notification_mod._render_html_template(
        "welcome.html",
        {"login_row_html": "<a href='https://app.example/login'>Login</a>"},
    )

    assert rendered == "<a href='https://app.example/login'>Login</a>"


def test_render_html_template_uses_safe_substitute_for_missing_tokens(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(notification_mod, "_EMAIL_TEMPLATE_ROOT", tmp_path)
    template = tmp_path / "welcome.html"
    template.write_text("Hello ${name} ${unknown}", encoding="utf-8")

    rendered = notification_mod._render_html_template("welcome.html", {"name": "Alice"})

    assert rendered == "Hello Alice ${unknown}"


def test_render_html_template_mixes_escaped_and_raw_html_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(notification_mod, "_EMAIL_TEMPLATE_ROOT", tmp_path)
    template = tmp_path / "welcome.html"
    template.write_text("${display_name} ${note_html}", encoding="utf-8")

    rendered = notification_mod._render_html_template(
        "welcome.html",
        {
            "display_name": "Tom & Jerry",
            "note_html": "<strong>Priority user</strong>",
        },
    )

    assert rendered == "Tom &amp; Jerry <strong>Priority user</strong>"
