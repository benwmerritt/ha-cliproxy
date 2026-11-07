"""Usage, reset and status sensors for CLIProxy accounts and providers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import CLIProxyConfigEntry, CLIProxyCoordinator
from .entity import AccountEntity, ProviderEntity, add_entities_as_they_appear


async def async_setup_entry(
    hass: HomeAssistant, entry: CLIProxyConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data

    def build(status: dict[str, Any]) -> Iterable[Entity]:
        for provider in status["providers"]:
            yield AccountsWithUsage(coordinator, provider, "accounts_with_usage", "Accounts with usage")
        for account in status["accounts"]:
            for limit in account["limits"]:
                yield LimitUsage(coordinator, account, limit)
            yield NextReset(coordinator, account, "next_reset", "Next reset")
            yield UsageBack(coordinator, account, "usage_back", "Usage back")
            yield AccountStatus(coordinator, account, "status", "Status")
            if account.get("credits") is not None:
                yield Credits(coordinator, account, "credits", "Credits")

    add_entities_as_they_appear(coordinator, async_add_entities, build)


def timestamp(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


class LimitUsage(AccountEntity, SensorEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator: CLIProxyCoordinator, account: dict[str, Any], limit: dict[str, Any]) -> None:
        super().__init__(coordinator, account, f"{limit['key']}_usage", f"{limit['name']} usage")
        self.limit_key = limit["key"]

    @property
    def limit(self) -> dict[str, Any] | None:
        account = self.account
        return next((item for item in account["limits"] if item["key"] == self.limit_key), None) if account else None

    @property
    def available(self) -> bool:
        return super().available and self.limit is not None

    @property
    def native_value(self) -> float | None:
        return self.limit["percent"] if self.limit else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        limit = self.limit or {}
        return {"resets_at": limit.get("resets_at"), "severity": limit.get("severity"), "active": limit.get("active")}


class NextReset(AccountEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-refresh-outline"

    @property
    def native_value(self) -> datetime | None:
        return timestamp(self.account["next_reset"]) if self.account else None


class UsageBack(AccountEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-sand"

    @property
    def native_value(self) -> datetime | None:
        return timestamp(self.account["usage_back_at"]) if self.account else None


class AccountStatus(AccountEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:account-check-outline"

    @property
    def native_value(self) -> str | None:
        return self.account["status"] if self.account else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        account = self.account or {}
        return {
            "status_message": account.get("status_message"),
            "plan": account.get("plan"),
            "banked_resets": account.get("banked_resets"),
            "observed_at": account.get("observed_at"),
        }


class Credits(AccountEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-multiple"
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        return self.account.get("credits") if self.account else None


class AccountsWithUsage(ProviderEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:account-multiple-check-outline"

    @property
    def native_value(self) -> int | None:
        return self.provider["with_usage"] if self.provider else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"accounts": self.provider["accounts"] if self.provider else None}
