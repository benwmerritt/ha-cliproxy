"""Management API responses shaped like CLIProxy 8.0.57's, with made-up accounts."""

from datetime import UTC, datetime

NOW = datetime(2026, 11, 7, 4, 0, tzinfo=UTC)

AUTH_FILES = {
    "files": [
        {
            "auth_index": "aaaa000000000001",
            "provider": "claude",
            "account": "work@example.com",
            "status": "active",
            "status_message": "",
            "disabled": False,
            "cooldowns": [],
            "id_token": "secret",
            "path": "/root/.cli-proxy-api/claude-work.json",
        },
        {
            "auth_index": "aaaa000000000002",
            "provider": "claude",
            "account": "home@example.com",
            "status": "error",
            "status_message": "quota exhausted",
            "disabled": False,
            "cooldowns": [
                {
                    "scope": "credential",
                    "reason": "credential_quota",
                    "retry_at": "2026-11-08T17:00:24.003867879Z",
                    "remaining_seconds": 134340,
                },
                {
                    "scope": "model",
                    "model_key": "claude-opus-5-5",
                    "reason": "quota",
                    "retry_at": "2026-11-08T17:00:24.003867879Z",
                },
            ],
        },
        {
            "auth_index": "bbbb000000000001",
            "provider": "codex",
            "account": "pro@example.com",
            "status": "active",
            "disabled": False,
            "cooldowns": [],
        },
        {"auth_index": "cccc000000000001", "provider": "kimi", "status": "disabled", "disabled": True},
    ]
}

HISTORY = {
    "accounts": {
        "claude/work@example.com": [
            {
                "t": "2026-11-07T03:31:38Z",
                "account": "claude/work@example.com",
                "provider": "claude",
                "windows": {"seven_day": 58},
                "limits": [
                    {
                        "kind": "weekly_all",
                        "group": "weekly",
                        "percent": 58,
                        "severity": "normal",
                        "resets_at": "2026-11-10T11:00:00Z",
                        "active": True,
                    },
                    {
                        "kind": "weekly_scoped",
                        "group": "weekly",
                        "model": "Fable",
                        "percent": 28,
                        "severity": "normal",
                        "resets_at": "2026-11-10T11:00:00Z",
                    },
                ],
            }
        ],
        "claude/home@example.com": [
            {
                "t": "2026-11-07T03:13:35Z",
                "account": "claude/home@example.com",
                "provider": "claude",
                "limits": [
                    {
                        "kind": "weekly_all",
                        "group": "weekly",
                        "percent": 100,
                        "severity": "critical",
                        "resets_at": "2026-11-08T17:00:00Z",
                        "active": True,
                    }
                ],
            }
        ],
        "codex/pro@example.com": [
            {
                "t": "2026-11-07T03:39:35Z",
                "account": "codex/pro@example.com",
                "provider": "codex",
                "window_minutes": {"primary": 10080},
                "limits": [{"kind": "primary", "group": "window", "percent": 60, "resets_at": "2026-11-11T07:15:22Z"}],
                "credits": 61371.04,
                "plan": "pro",
            },
            {"t": "2026-11-07T03:39:36Z", "account": "codex/pro@example.com", "provider": "codex", "banked_resets": 1},
        ],
    }
}
