from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CLIProxyConfigEntry
from .entity import AccountEntity, ProviderEntity, add_entities_as_they_appear


async def async_setup_entry(
    hass: HomeAssistant, entry: CLIProxyConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data

    def build(status: dict[str, Any]) -> Iterable[Entity]:
        for provider in status["providers"]:
            yield ProviderOutOfUsage(coordinator, provider, "out_of_usage", "Out of usage")
        for account in status["accounts"]:
            yield AccountOutOfUsage(coordinator, account, "out_of_usage", "Out of usage")

    add_entities_as_they_appear(coordinator, async_add_entities, build)


class AccountOutOfUsage(AccountEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        return self.account["out_of_usage"] if self.account else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        account = self.account or {}
        return {"usage_back_at": account.get("usage_back_at"), "account": account.get("account")}


class ProviderOutOfUsage(ProviderEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        return self.provider["out_of_usage"] if self.provider else None
