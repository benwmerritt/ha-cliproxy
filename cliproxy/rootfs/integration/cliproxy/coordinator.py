from __future__ import annotations

import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .changes import changes
from .const import DOMAIN, PROVIDER_PREFIX, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type CLIProxyConfigEntry = ConfigEntry[CLIProxyCoordinator]


async def fetch_status(session: aiohttp.ClientSession, url: str, token: str) -> dict[str, Any]:
    async with session.get(
        f"{url}/api/status",
        headers={"Authorization": f"Bearer {token}"},
        timeout=aiohttp.ClientTimeout(total=45),
    ) as response:
        body = await response.json(content_type=None)
        if response.status >= 400:
            raise UpdateFailed(body.get("error") if isinstance(body, dict) else f"HTTP {response.status}")
        return body


def device_identifier(account_id: str | None = None, provider: str | None = None) -> tuple[str, str]:
    return (DOMAIN, account_id if account_id else f"{PROVIDER_PREFIX}{provider}")


class CLIProxyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: CLIProxyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CLIProxyConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await fetch_status(self._session, self.config_entry.data["url"], self.config_entry.data["token"])
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise UpdateFailed(f"Could not reach the CLIProxy add-on: {error}") from error
        self._register_providers(status)
        if self.data is not None:
            self._fire(changes(self.data, status))
        return status

    def _register_providers(self, status: dict[str, Any]) -> None:
        devices = dr.async_get(self.hass)
        for provider in status["providers"]:
            devices.async_get_or_create(
                config_entry_id=self.config_entry.entry_id,
                identifiers={device_identifier(provider=provider["provider"])},
                name=provider["name"],
                manufacturer="CLIProxy",
                model="Provider",
                entry_type=dr.DeviceEntryType.SERVICE,
            )

    def _fire(self, events: list[tuple[str, dict[str, Any]]]) -> None:
        devices = dr.async_get(self.hass)
        for event_type, data in events:
            identifier = device_identifier(data.get("account_id"), data.get("provider"))
            device = devices.async_get_device_by_identifier(identifier, self.config_entry.entry_id)
            self.hass.bus.async_fire(event_type, {**data, "device_id": device.id if device else None})
