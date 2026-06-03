"""Thin async client for the GeoSphere Austria Data Hub nowcast endpoint."""

from __future__ import annotations

import asyncio

import aiohttp

from .const import BASE_URL, NOWCAST_RESOURCE, PARAMETERS, REQUEST_TIMEOUT


class GeoSphereApiError(Exception):
    """Base error for the GeoSphere API client."""


class GeoSphereConnectionError(GeoSphereApiError):
    """Raised on network failure or timeout reaching the API."""


class GeoSphereDataError(GeoSphereApiError):
    """Raised on a non-200 response or undecodable/invalid payload."""


class GeoSphereApiClient:
    """Fetches raw nowcast JSON. Parsing lives in the coordinator (testable)."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_get_nowcast(self, latitude: float, longitude: float) -> dict:
        """Return the raw nowcast JSON for a point, or raise a typed error."""
        url = f"{BASE_URL}{NOWCAST_RESOURCE}"
        params = {
            "parameters": ",".join(PARAMETERS),
            "lat_lon": f"{latitude},{longitude}",
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(url, params=params) as resp:
                    if resp.status != 200:
                        raise GeoSphereDataError(
                            f"GeoSphere API returned HTTP {resp.status}"
                        )
                    try:
                        return await resp.json()
                    except (aiohttp.ClientError, ValueError) as err:
                        raise GeoSphereDataError(
                            "GeoSphere API returned invalid JSON"
                        ) from err
        except GeoSphereApiError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise GeoSphereConnectionError(
                f"Error connecting to GeoSphere API: {err}"
            ) from err
