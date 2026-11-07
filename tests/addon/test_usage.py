from aiohttp import web

from sample import AUTH_FILES, HISTORY, NOW
from usage import open_session, summarise


def by_account(status):
    return {account["account"]: account for account in status["accounts"]}


def test_quota_cooldown_marks_an_account_out_of_usage_until_it_ends():
    home = by_account(summarise(AUTH_FILES, HISTORY, NOW))["claude/home@example.com"]

    assert home["out_of_usage"] is True
    assert home["usage_back_at"] == "2026-11-08T17:00:24.003867+00:00"
    assert home["next_reset"] == "2026-11-08T17:00:00+00:00"


def test_an_account_with_room_left_is_not_out_of_usage():
    work = by_account(summarise(AUTH_FILES, HISTORY, NOW))["claude/work@example.com"]

    assert work["out_of_usage"] is False
    assert work["usage_back_at"] is None
    assert [(limit["key"], limit["name"], limit["percent"]) for limit in work["limits"]] == [
        ("weekly_all", "Weekly", 58.0),
        ("weekly_scoped_fable", "Weekly Fable", 28.0),
    ]


def test_codex_limits_come_from_the_newest_row_that_has_them():
    codex = by_account(summarise(AUTH_FILES, HISTORY, NOW))["codex/pro@example.com"]

    assert codex["limits"][0]["name"] == "Weekly"
    assert codex["limits"][0]["percent"] == 60.0
    assert codex["banked_resets"] == 1
    assert codex["plan"] == "pro"
    assert codex["credits"] == 61371.04


def test_disabled_accounts_and_credentials_are_left_out():
    status = summarise(AUTH_FILES, HISTORY, NOW)

    assert {account["provider"] for account in status["accounts"]} == {"claude", "codex"}
    assert "secret" not in str(status)
    assert "/root/" not in str(status)


def test_a_provider_is_out_of_usage_only_when_every_account_is():
    providers = {p["provider"]: p for p in summarise(AUTH_FILES, HISTORY, NOW)["providers"]}

    assert providers["claude"] == {
        "provider": "claude",
        "name": "Claude",
        "accounts": 2,
        "with_usage": 1,
        "out_of_usage": False,
    }

    exhausted = {"files": [f for f in AUTH_FILES["files"] if f["provider"] == "claude" and "home" in f["account"]]}
    assert summarise(exhausted, HISTORY, NOW)["providers"][0]["out_of_usage"] is True


def test_an_active_limit_at_100_percent_counts_without_a_cooldown():
    files = {"files": [{**AUTH_FILES["files"][1], "cooldowns": []}]}

    home = summarise(files, HISTORY, NOW)["accounts"][0]

    assert home["out_of_usage"] is True
    assert home["usage_back_at"] == "2026-11-08T17:00:00+00:00"


def test_a_full_window_does_not_count_while_credits_pay_for_usage():
    credits = 61302.18
    history = {
        "accounts": {
            "codex/pro@example.com": [
                {
                    "t": "2026-11-07T03:39:35Z",
                    "window_minutes": {"primary": 43200},
                    "limits": [
                        {"kind": "primary", "percent": 100, "resets_at": "2026-11-30T04:58:29Z", "active": True}
                    ],
                    "credits": credits,
                }
            ]
        }
    }
    files = {"files": [AUTH_FILES["files"][2]]}

    assert summarise(files, history, NOW)["accounts"][0]["out_of_usage"] is False
    history["accounts"]["codex/pro@example.com"][0]["credits"] = 0
    assert summarise(files, history, NOW)["accounts"][0]["out_of_usage"] is True


async def test_connect_address_reaches_the_proxy_while_keeping_its_hostname(aiohttp_server):
    seen = {}

    async def handler(request):
        seen["host"] = request.host
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", handler)
    server = await aiohttp_server(app)

    url = f"http://cliproxy.tailnet.invalid:{server.port}"
    async with open_session(url, "127.0.0.1") as session, session.get(url + "/") as response:
        assert await response.json() == {"ok": True}

    assert seen["host"] == f"cliproxy.tailnet.invalid:{server.port}"
