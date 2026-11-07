"""Works out which automation events a new status reading should fire."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .const import EVENT_OUT_OF_USAGE, EVENT_USAGE_RESET, EVENT_USAGE_RESTORED

MIN_RESET_ADVANCE = timedelta(minutes=30)

Status = dict[str, Any]
Event = tuple[str, Status]


def changes(previous: Status, current: Status) -> list[Event]:
    return account_changes(previous, current) + provider_changes(previous, current)


def account_changes(previous: Status, current: Status) -> list[Event]:
    before = {account["id"]: account for account in previous.get("accounts", [])}
    events: list[Event] = []
    for account in current.get("accounts", []):
        old = before.get(account["id"])
        if old is None:
            continue
        identity = {
            "scope": "account",
            "account_id": account["id"],
            "account": account["account"],
            "provider": account["provider"],
        }
        if account["out_of_usage"] and not old["out_of_usage"]:
            events.append((EVENT_OUT_OF_USAGE, {**identity, "usage_back_at": account["usage_back_at"]}))
        if old["out_of_usage"] and not account["out_of_usage"]:
            events.append((EVENT_USAGE_RESTORED, identity))
        events.extend((EVENT_USAGE_RESET, {**identity, **reset}) for reset in limit_resets(old, account))
    return events


def limit_resets(old: Status, new: Status) -> list[Status]:
    before = {limit["key"]: limit for limit in old.get("limits", [])}
    resets = []
    for limit in new.get("limits", []):
        previous = before.get(limit["key"])
        if not previous or not previous.get("resets_at") or not limit.get("resets_at"):
            continue
        if parse(limit["resets_at"]) - parse(previous["resets_at"]) < MIN_RESET_ADVANCE:
            continue
        resets.append(
            {
                "limit": limit["key"],
                "limit_name": limit["name"],
                "previous_percent": previous["percent"],
                "percent": limit["percent"],
                "resets_at": limit["resets_at"],
            }
        )
    return resets


def provider_changes(previous: Status, current: Status) -> list[Event]:
    before = {provider["provider"]: provider for provider in previous.get("providers", [])}
    events: list[Event] = []
    for provider in current.get("providers", []):
        old = before.get(provider["provider"])
        if old is None or old["out_of_usage"] == provider["out_of_usage"]:
            continue
        event = EVENT_OUT_OF_USAGE if provider["out_of_usage"] else EVENT_USAGE_RESTORED
        events.append((event, {"scope": "provider", "provider": provider["provider"]}))
    return events


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)
