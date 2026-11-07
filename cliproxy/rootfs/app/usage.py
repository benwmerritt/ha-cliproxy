"""Reads CLIProxy's management API and reduces it to per-account usage."""

from __future__ import annotations

import re
import socket
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

NANOSECONDS = re.compile(r"(\.\d{6})\d+")
QUOTA_COOLDOWN_REASONS = {"credential_quota", "quota"}
HISTORY_ROWS = 12
WINDOW_NAMES = {300: "5-hour", 1440: "Daily", 10080: "Weekly", 43200: "Monthly"}
KIND_NAMES = {
    "five_hour": "5-hour",
    "seven_day": "Weekly",
    "weekly_all": "Weekly",
    "weekly_scoped": "Weekly",
    "primary": "Primary",
    "secondary": "Secondary",
}
PROVIDER_NAMES = {"claude": "Claude", "codex": "Codex", "meta": "Meta", "xai": "xAI", "kimi": "Kimi"}

Status = dict[str, Any]


class PinnedResolver(AbstractResolver):
    """Resolves the proxy's hostname to a fixed address.

    Home Assistant OS cannot resolve tailnet (*.ts.net) names, and Tailscale
    Serve needs the name in the TLS handshake, so the URL keeps the name and
    only the connection goes to the address.
    """

    def __init__(self, hostname: str, address: str) -> None:
        self._hostname = hostname
        self._address = address
        self._fallback = aiohttp.ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        if host != self._hostname:
            return await self._fallback.resolve(host, port, family)
        return [
            ResolveResult(
                hostname=host,
                host=self._address,
                port=port,
                family=socket.AF_INET6 if ":" in self._address else socket.AF_INET,
                proto=0,
                flags=socket.AI_NUMERICHOST,
            )
        ]

    async def close(self) -> None:
        await self._fallback.close()


def open_session(url: str, connect_address: str | None) -> aiohttp.ClientSession:
    resolver = PinnedResolver(urlsplit(url).hostname or "", connect_address) if connect_address else None
    return aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=resolver))


async def fetch_status(session: aiohttp.ClientSession, url: str, management_key: str, now: datetime) -> Status:
    headers = {"Authorization": f"Bearer {management_key}"}
    timeout = aiohttp.ClientTimeout(total=30)
    base = url.rstrip("/")
    async with session.get(f"{base}/v0/management/auth-files", headers=headers, timeout=timeout) as response:
        response.raise_for_status()
        auth_files = await response.json()
    async with session.get(
        f"{base}/v0/management/quota-history", params={"limit": HISTORY_ROWS}, headers=headers, timeout=timeout
    ) as response:
        if response.status == 404:
            history = {}
        else:
            response.raise_for_status()
            history = await response.json()
    return summarise(auth_files, history, now)


def summarise(auth_files: dict[str, Any], history: dict[str, Any], now: datetime) -> Status:
    readings = latest_readings(history.get("accounts") or {})
    accounts = [
        account_status(file, readings.get(account_key(file), {}), now)
        for file in auth_files.get("files") or []
        if not file.get("disabled")
    ]
    accounts.sort(key=lambda account: (account["provider"], account["name"]))
    return {"fetched_at": now.isoformat(), "accounts": accounts, "providers": provider_status(accounts)}


def account_key(file: dict[str, Any]) -> str:
    return f"{file.get('provider') or 'unknown'}/{account_name(file)}"


def account_name(file: dict[str, Any]) -> str:
    return file.get("account") or file.get("email") or file.get("label") or file.get("name") or "unknown"


def latest_readings(rows_by_account: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    readings: dict[str, dict[str, Any]] = {}
    for account, rows in rows_by_account.items():
        reading: dict[str, Any] = {}
        for row in sorted(rows, key=lambda row: row.get("t") or ""):
            if "limits" in row:
                reading.update({key: value for key, value in row.items() if key != "banked_resets"})
            if "banked_resets" in row:
                reading["banked_resets"] = row["banked_resets"]
        readings[account] = reading
    return readings


def account_status(file: dict[str, Any], reading: dict[str, Any], now: datetime) -> Status:
    provider = file.get("provider") or "unknown"
    limits = [limit_status(limit, reading) for limit in reading.get("limits") or []]
    cooldown_until = quota_cooldown_until(file.get("cooldowns") or [], now)
    has_credits = bool(reading.get("credit_unlimited")) or (reading.get("credits") or 0) > 0
    exhausted = [] if has_credits else [limit for limit in limits if limit["active"] and limit["percent"] >= 100]
    out_of_usage = cooldown_until is not None or bool(exhausted)
    upcoming = sorted(
        (limit["resets_at"] for limit in limits if limit["resets_at"] and parse_time(limit["resets_at"]) > now),
        key=parse_time,
    )
    back_at = cooldown_until or max(
        (limit["resets_at"] for limit in exhausted if limit["resets_at"]), key=parse_time, default=None
    )
    return {
        "id": file.get("auth_index") or account_key(file),
        "account": account_key(file),
        "provider": provider,
        "provider_name": provider_name(provider),
        "name": account_name(file),
        "status": file.get("status") or "unknown",
        "status_message": file.get("status_message") or None,
        "out_of_usage": out_of_usage,
        "usage_back_at": back_at if out_of_usage else None,
        "next_reset": upcoming[0] if upcoming else None,
        "plan": reading.get("plan"),
        "credits": reading.get("credits"),
        "banked_resets": reading.get("banked_resets"),
        "observed_at": utc(reading.get("t")),
        "limits": limits,
    }


def limit_status(limit: dict[str, Any], reading: dict[str, Any]) -> Status:
    kind = limit.get("kind") or "limit"
    model = limit.get("model") or None
    minutes = (reading.get("window_minutes") or {}).get(kind)
    name = WINDOW_NAMES.get(minutes) or KIND_NAMES.get(kind) or kind.replace("_", " ").capitalize()
    return {
        "key": f"{kind}_{model.lower()}" if model else kind,
        "name": f"{name} {model}" if model else name,
        "model": model,
        "percent": float(limit.get("percent") or 0),
        "severity": limit.get("severity"),
        "resets_at": utc(limit.get("resets_at")),
        "active": bool(limit.get("active")),
    }


def quota_cooldown_until(cooldowns: list[dict[str, Any]], now: datetime) -> str | None:
    until = [
        cooldown["retry_at"]
        for cooldown in cooldowns
        if cooldown.get("scope") == "credential"
        and cooldown.get("reason") in QUOTA_COOLDOWN_REASONS
        and cooldown.get("retry_at")
        and parse_time(cooldown["retry_at"]) > now
    ]
    return utc(max(until, key=parse_time)) if until else None


def provider_status(accounts: list[Status]) -> list[Status]:
    providers: dict[str, Status] = {}
    for account in accounts:
        provider = providers.setdefault(
            account["provider"],
            {"provider": account["provider"], "name": account["provider_name"], "accounts": 0, "with_usage": 0},
        )
        provider["accounts"] += 1
        provider["with_usage"] += not account["out_of_usage"]
    for provider in providers.values():
        provider["out_of_usage"] = provider["with_usage"] == 0
    return sorted(providers.values(), key=lambda provider: provider["provider"])


def provider_name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider, provider.capitalize())


def utc(value: str | None) -> str | None:
    return parse_time(value).astimezone(UTC).isoformat() if value else None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(NANOSECONDS.sub(r"\1", value.replace("Z", "+00:00")))
