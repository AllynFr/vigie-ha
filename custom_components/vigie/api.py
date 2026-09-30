"""Small async client for the Vigie public API (v1)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .const import API_PREFIX, SHORT_PREFIX

REQUEST_TIMEOUT = 20


class VigieError(Exception):
    """Base error. `code` is the stable Vigie error code when known."""

    def __init__(self, message: str = "", code: str | None = None, status: int | None = None) -> None:
        super().__init__(message or code or "vigie_error")
        self.message = message
        self.code = code
        self.status = status


class VigieConnectionError(VigieError):
    """Network error, timeout or unexpected server answer."""


class VigieAuthError(VigieError):
    """401: key missing, invalid, expired or revoked."""


class VigieForbiddenError(VigieError):
    """403: ability missing on the key, or option disabled on the car."""

    def __init__(self, message: str, code: str | None, ability: str | None = None) -> None:
        super().__init__(message, code, 403)
        self.ability = ability


class VigieRateLimitError(VigieError):
    """429: per-key limit or wake-up limit reached."""

    def __init__(self, message: str, code: str | None, retry_after: int | None) -> None:
        super().__init__(message, code, 429)
        self.retry_after = retry_after


class VigieAsleepError(VigieError):
    """409 vehicle_asleep: commands never wake the car."""


class VigieCommandError(VigieError):
    """Command refused (422 command_rejected / validation, 409, 502 tesla_error...)."""

    def __init__(self, message: str, code: str | None, status: int, reason: str | None = None) -> None:
        super().__init__(message, code, status)
        self.reason = reason


class VigieNotFoundError(VigieError):
    """404: unknown vehicle for this key."""


def normalize_url(url: str) -> str:
    """Return the instance base URL without trailing slash nor /api/v1 (or /v1 on an api. host)."""
    url = url.strip().rstrip("/")
    if url.endswith(API_PREFIX):
        url = url[: -len(API_PREFIX)]
    elif url.endswith(SHORT_PREFIX) and urlsplit(url).netloc.startswith("api."):
        url = url[: -len(SHORT_PREFIX)]
    return url


def app_url(base_url: str) -> str:
    """Web app address for a base URL: https://api.iodek.fr -> https://iodek.fr (the API host has no pages)."""
    parts = urlsplit(base_url)
    if parts.netloc.startswith("api."):
        return f"{parts.scheme}://{parts.netloc[4:]}"
    return base_url


class VigieClient:
    """Wraps the endpoints used by Home Assistant. The key is never logged."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        api_key: str,
        language: str | None = None,
    ) -> None:
        self._session = session
        self.base_url = normalize_url(base_url)
        self._api_key = api_key
        self._language = language

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        if self._language:
            headers["Accept-Language"] = self._language
        url = f"{self.base_url}{API_PREFIX}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    body = None
                status = resp.status
                retry_after = resp.headers.get("Retry-After")
        except (TimeoutError, aiohttp.ClientError) as err:
            raise VigieConnectionError(str(err) or type(err).__name__) from err

        if 200 <= status < 300:
            if body is None:
                raise VigieConnectionError("invalid_json", status=status)
            return body

        data = body if isinstance(body, dict) else {}
        message = str(data.get("message") or "")
        code = data.get("code")
        if status == 401:
            raise VigieAuthError(message, code or "api_key_required", status)
        if status == 403:
            raise VigieForbiddenError(message, code, data.get("ability") or data.get("option"))
        if status == 404:
            raise VigieNotFoundError(message, code or "not_found", status)
        if status == 429:
            try:
                seconds = int(retry_after) if retry_after else None
            except ValueError:
                seconds = None
            raise VigieRateLimitError(message, code or "rate_limited", seconds)
        if status == 409 and code == "vehicle_asleep":
            raise VigieAsleepError(message, code, status)
        if method == "POST" and status in (409, 422, 428, 502):
            raise VigieCommandError(message, code, status, data.get("reason"))
        raise VigieConnectionError(message or f"http_{status}", code, status)

    async def vehicles(self) -> dict[str, Any]:
        """GET /vehicles. Returns the whole body ({"data": [...]})."""
        return await self._request("GET", "/vehicles")

    async def state(self, vehicle_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/vehicles/{vehicle_id}/state")

    async def battery(self, vehicle_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/vehicles/{vehicle_id}/battery")

    async def charges(self, vehicle_id: int, per_page: int = 1) -> dict[str, Any]:
        return await self._request("GET", f"/vehicles/{vehicle_id}/charges", params={"per_page": per_page})

    async def command(self, vehicle_id: int, command: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", f"/vehicles/{vehicle_id}/commands/{command}", json=body or {})

    async def wake(self, vehicle_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/vehicles/{vehicle_id}/wake")

    async def send_location(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /me/location: the user's last position (one per user on the server)."""
        return await self._request("POST", "/me/location", json=payload)

    async def probe_ability(self, vehicle_id: int, ability: str, command: str) -> bool | None:
        """Tell whether the key holds `ability` without reaching the car.

        The command is sent with an empty body: a key without the ability gets
        403 ability_missing; with it, the API answers 403 option_disabled /
        commands_disabled (option off) or 422 (body invalid) before any call to
        Tesla. Returns None when the answer is not conclusive.
        """
        try:
            await self._request("POST", f"/vehicles/{vehicle_id}/commands/{command}", json={})
        except VigieForbiddenError as err:
            if err.code == "ability_missing":
                return False
            return True
        except VigieCommandError as err:
            return err.status == 422
        except VigieError:
            return None
        # A 2xx here would mean the body was accepted: should never happen.
        return True
