from aiohttp import web

from sample import AUTH_FILES, HISTORY, NOW
from usage import open_session, summarise


def by_account(status):
    return {account["account"]: account for account in status["accounts"]}


def test_quota_cooldown_marks_an_account_out_of_usage_until_it_ends():
    home = by_account(summarise(AUTH_FILES, HISTORY, NOW))["claude/home@example.com"]

    assert home["out_of_usage"] is True
    assert home["using_credits"] is False
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

    on_credits = summarise(files, history, NOW)["accounts"][0]
    assert (on_credits["out_of_usage"], on_credits["using_credits"]) == (False, True)
    history["accounts"]["codex/pro@example.com"][0]["credits"] = 0
    spent = summarise(files, history, NOW)["accounts"][0]
    assert (spent["out_of_usage"], spent["using_credits"]) == (True, False)


def test_a_json_error_from_the_provider_reads_as_its_message():
    raw = '{"type":"error","error":{"type":"rate_limit_error","message":"This request would exceed your account\'s rate limit."},"request_id":"req_1"}'
    files = {"files": [{**AUTH_FILES["files"][1], "status_message": raw}]}

    message = summarise(files, HISTORY, NOW)["accounts"][0]["status_message"]

    assert message == "This request would exceed your account's rate limit."


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


def codex_reading(*limits, window_minutes=None):
    return {
        "accounts": {
            "codex/pro@example.com": [
                {
                    "t": "2026-11-07T03:39:35Z",
                    "window_minutes": window_minutes or {},
                    "limits": list(limits),
                    "plan": "pro",
                }
            ]
        }
    }


CODEX_FILES = {"files": [AUTH_FILES["files"][2]]}


def test_a_full_model_or_code_review_pool_leaves_the_account_usable():
    history = codex_reading(
        {"kind": "primary", "group": "window", "percent": 60, "resets_at": "2026-11-11T07:15:22Z"},
        {
            "kind": "primary",
            "group": "additional",
            "model": "GPT-5.3-Codex-Spark",
            "percent": 100,
            "resets_at": "2026-11-09T00:00:00Z",
            "active": True,
        },
        {
            "kind": "primary",
            "group": "code_review",
            "percent": 100,
            "resets_at": "2026-11-09T00:00:00Z",
            "active": True,
        },
        window_minutes={"primary": 10080, "additional:GPT-5.3-Codex-Spark:primary": 300, "code_review:primary": 10080},
    )

    codex = summarise(CODEX_FILES, history, NOW)["accounts"][0]

    assert codex["out_of_usage"] is False
    assert [(limit["key"], limit["name"]) for limit in codex["limits"]] == [
        ("primary", "Weekly"),
        ("additional_primary_gpt_5_3_codex_spark", "5-hour GPT-5.3-Codex-Spark"),
        ("code_review_primary", "Weekly code review"),
    ]


def test_a_full_window_that_has_already_reset_no_longer_counts():
    history = codex_reading(
        {"kind": "primary", "group": "window", "percent": 100, "resets_at": "2026-11-07T03:00:00Z", "active": True}
    )

    codex = summarise(CODEX_FILES, history, NOW)["accounts"][0]

    assert codex["out_of_usage"] is False
    assert codex["usage_back_at"] is None
    assert codex["limits"][0] | {"key": None, "name": None} == {
        "key": None,
        "name": None,
        "model": None,
        "account_wide": True,
        "percent": 0.0,
        "severity": None,
        "resets_at": None,
        "active": False,
    }


def test_a_timestamp_the_addon_cannot_read_is_left_blank():
    history = codex_reading({"kind": "primary", "group": "window", "percent": 40, "resets_at": "next tuesday"})

    codex = summarise(CODEX_FILES, history, NOW)["accounts"][0]

    assert codex["limits"][0]["resets_at"] is None
    assert codex["limits"][0]["percent"] == 40.0
