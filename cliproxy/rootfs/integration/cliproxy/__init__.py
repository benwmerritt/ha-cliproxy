from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .coordinator import CLIProxyConfigEntry, CLIProxyCoordinator, device_identifier

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: CLIProxyConfigEntry) -> bool:
    coordinator = CLIProxyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CLIProxyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CLIProxyConfigEntry, device: DeviceEntry
) -> bool:
    status = entry.runtime_data.data
    current = {device_identifier(account_id=account["id"]) for account in status["accounts"]} | {
        device_identifier(provider=provider["provider"]) for provider in status["providers"]
    }
    return not device.identifiers & current
