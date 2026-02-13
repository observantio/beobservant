"""Silence-focused operations for AlertManagerService."""

from typing import Dict, List, Optional

import httpx

from models.access.auth_models import TokenData
from models.alerting.silences import Silence, SilenceCreate, Visibility


def apply_silence_metadata(service, silence: Silence) -> Silence:
    data = service.decode_silence_comment(silence.comment)
    silence.comment = data["comment"]
    silence.visibility = data["visibility"]
    silence.shared_group_ids = data["shared_group_ids"]
    return silence


def silence_accessible(service, silence: Silence, current_user: TokenData) -> bool:
    visibility = silence.visibility or Visibility.TENANT.value
    if silence.created_by == current_user.username:
        return True
    if visibility == Visibility.TENANT.value:
        return True
    if visibility == Visibility.GROUP.value:
        user_group_ids = getattr(current_user, "group_ids", []) or []
        return any(group_id in silence.shared_group_ids for group_id in user_group_ids)
    return False


async def get_silences(service, filter_labels: Optional[Dict[str, str]] = None) -> List[Silence]:
    params = {}
    if filter_labels:
        filters = [f'{key}="{value}"' for key, value in filter_labels.items()]
        params["filter"] = filters

    try:
        response = await service._client.get(
            f"{service.alertmanager_url}/api/v2/silences",
            params=params,
        )
        response.raise_for_status()
        return [Silence(**silence) for silence in response.json()]
    except httpx.HTTPError as exc:
        service.logger.error("Error fetching silences: %s", exc)
        return []


async def get_silence(service, silence_id: str) -> Optional[Silence]:
    try:
        response = await service._client.get(
            f"{service.alertmanager_url}/api/v2/silence/{silence_id}",
        )
        response.raise_for_status()
        return Silence(**response.json())
    except httpx.HTTPError as exc:
        service.logger.error("Error fetching silence %s: %s", silence_id, exc)
        return None


async def create_silence(service, silence: SilenceCreate) -> Optional[str]:
    try:
        silence_data = silence.model_dump(by_alias=True, exclude_none=True)
        response = await service._client.post(
            f"{service.alertmanager_url}/api/v2/silences",
            json=silence_data,
        )
        response.raise_for_status()
        return response.json().get("silenceID")
    except httpx.HTTPError as exc:
        service.logger.error("Error creating silence: %s", exc)
        return None


async def delete_silence(service, silence_id: str) -> bool:
    try:
        response = await service._client.delete(
            f"{service.alertmanager_url}/api/v2/silence/{silence_id}",
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        service.logger.error("Error deleting silence %s: %s", silence_id, exc)
        return False


async def update_silence(service, silence_id: str, silence: SilenceCreate) -> Optional[str]:
    await delete_silence(service, silence_id)
    return await create_silence(service, silence)
