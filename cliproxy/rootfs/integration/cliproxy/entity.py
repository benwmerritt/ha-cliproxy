from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import CLIProxyCoordinator, device_identifier


def provider_device(provider: dict[str, Any]) -> DeviceInfo:
    return DeviceInfo(
        identifiers={device_identifier(provider=provider["provider"])},
        name=provider["name"],
        manufacturer="CLIProxy",
        model="Provider",
        entry_type=DeviceEntryType.SERVICE,
    )


def account_device(coordinator: CLIProxyCoordinator, account: dict[str, Any]) -> DeviceInfo:
    provider = dr.async_get(coordinator.hass).async_get_device_by_identifier(
        device_identifier(provider=account["provider"]), coordinator.config_entry.entry_id
    )
    info = DeviceInfo(
        identifiers={device_identifier(account["id"])},
        name=f"{account['provider_name']} {account['name']}",
        manufacturer="CLIProxy",
        model=f"{account['provider_name']} account",
        entry_type=DeviceEntryType.SERVICE,
    )
    if provider:
        info["via_device_id"] = provider.id
    return info


def add_entities_as_they_appear(
    coordinator: CLIProxyCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    build: Callable[[dict[str, Any]], Iterable[Entity]],
) -> None:
    known: set[str] = set()

    @callback
    def add_new() -> None:
        new = [entity for entity in build(coordinator.data) if entity.unique_id not in known]
        known.update(entity.unique_id for entity in new)
        if new:
            async_add_entities(new)

    add_new()
    coordinator.config_entry.async_on_unload(coordinator.async_add_listener(add_new))


class AccountEntity(CoordinatorEntity[CLIProxyCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CLIProxyCoordinator, account: dict[str, Any], key: str, name: str) -> None:
        super().__init__(coordinator)
        self.account_id = account["id"]
        self._attr_unique_id = f"{account['id']}_{key}"
        self._attr_name = name
        self._attr_device_info = account_device(coordinator, account)

    @property
    def account(self) -> dict[str, Any] | None:
        return next((a for a in self.coordinator.data["accounts"] if a["id"] == self.account_id), None)

    @property
    def available(self) -> bool:
        return super().available and self.account is not None


class ProviderEntity(CoordinatorEntity[CLIProxyCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: CLIProxyCoordinator, provider: dict[str, Any], key: str, name: str) -> None:
        super().__init__(coordinator)
        self.provider_key = provider["provider"]
        self._attr_unique_id = f"provider_{provider['provider']}_{key}"
        self._attr_name = name
        self._attr_device_info = provider_device(provider)

    @property
    def provider(self) -> dict[str, Any] | None:
        return next((p for p in self.coordinator.data["providers"] if p["provider"] == self.provider_key), None)

    @property
    def available(self) -> bool:
        return super().available and self.provider is not None
