from typing import Optional


def normalize_visibility(
    value: Optional[str],
    *,
    default_value: str = "private",
    public_alias: str = "tenant",
    allowed: set[str] | None = None,
) -> str:
    normalized = str(value or default_value).strip().lower()
    allowed_values = allowed or {"tenant", "group", "private"}
    if normalized in allowed_values:
        return normalized
    if normalized == "public":
        return public_alias
    return default_value


def normalize_storage_visibility(value: Optional[str]) -> str:
    normalized = str(value or "public").strip().lower()
    if normalized in {"public", "private", "group"}:
        return normalized
    if normalized == "tenant":
        return "public"
    return "public"
