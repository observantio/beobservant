"""Folder-focused helpers for GrafanaProxyService."""

from typing import Optional


def extract_folder_uid_from_path(service, path: str) -> Optional[str]:
    patterns = [
        r"^/grafana/dashboards/f/([^/?]+)",
        r"^/grafana/api/folders/([^/?]+)",
    ]
    import re
    for pattern in patterns:
        match = re.match(pattern, path)
        if match:
            return match.group(1)
    return None


async def resolve_folder_uid(service, folder_id: Optional[int]) -> Optional[str]:
    if not folder_id:
        return None
    try:
        folders = await service.grafana_service.get_folders()
        for folder in folders:
            if folder.id == folder_id:
                return folder.uid
    except Exception as exc:
        service.logger.debug("Unable to resolve folder uid for created dashboard: %s", exc)
    return None
