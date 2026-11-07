import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import server
from sample import AUTH_FILES, HISTORY


async def fake_proxy(aiohttp_server, key="mgmt-key", with_history=True):
    async def auth_files(request):
        if request.headers.get("Authorization") != f"Bearer {key}":
            return web.json_response({"error": "bad key"}, status=401)
        return web.json_response(AUTH_FILES)

    async def history(request):
        return web.json_response(HISTORY)

    app = web.Application()
    app.router.add_get("/v0/management/auth-files", auth_files)
    if with_history:
        app.router.add_get("/v0/management/quota-history", history)
    return await aiohttp_server(app)


async def addon_client(proxy_url, key="mgmt-key"):
    app = web.Application(middlewares=[server.require_ingress_or_token])
    app["cache"] = server.StatusCache({"url": proxy_url, "management_key": key})
    app["token"] = "addon-token"
    app.router.add_get("/", server.panel)
    app.router.add_get("/api/status", server.status)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def test_status_needs_the_addon_token_outside_ingress(aiohttp_server):
    proxy = await fake_proxy(aiohttp_server)
    client = await addon_client(str(proxy.make_url("")))
    try:
        assert (await client.get("/api/status")).status == 401
        assert (await client.get("/api/status", headers={"Authorization": "Bearer wrong"})).status == 401

        response = await client.get("/api/status", headers={"Authorization": "Bearer addon-token"})
        body = await response.json()
        assert response.status == 200
        assert [account["account"] for account in body["accounts"]] == [
            "claude/home@example.com",
            "claude/work@example.com",
            "codex/pro@example.com",
        ]
        assert body["proxy_url"] == str(proxy.make_url("")).rstrip("/")
    finally:
        await client.close()


async def test_a_rejected_management_key_reports_an_error(aiohttp_server):
    proxy = await fake_proxy(aiohttp_server)
    client = await addon_client(str(proxy.make_url("")), key="wrong")
    try:
        response = await client.get("/api/status", headers={"Authorization": "Bearer addon-token"})
        assert response.status == 502
        assert "401" in (await response.json())["error"]
    finally:
        await client.close()


async def test_a_proxy_without_quota_history_still_lists_its_accounts(aiohttp_server):
    proxy = await fake_proxy(aiohttp_server, with_history=False)
    client = await addon_client(str(proxy.make_url("")))
    try:
        response = await client.get("/api/status", headers={"Authorization": "Bearer addon-token"})
        body = await response.json()
        assert response.status == 200
        assert [(a["account"], a["limits"]) for a in body["accounts"]] == [
            ("claude/home@example.com", []),
            ("claude/work@example.com", []),
            ("codex/pro@example.com", []),
        ]
        assert by_name(body)["claude/home@example.com"]["out_of_usage"] is True
    finally:
        await client.close()


def by_name(status):
    return {account["account"]: account for account in status["accounts"]}


async def test_panel_is_served_to_ingress(aiohttp_server, monkeypatch):
    monkeypatch.setattr(server, "INGRESS_PEER", "127.0.0.1")
    proxy = await fake_proxy(aiohttp_server)
    client = await addon_client(str(proxy.make_url("")))
    try:
        response = await client.get("/")
        assert response.status == 200
        assert "<title>CLIProxy</title>" in await response.text()
        assert (await client.get("/api/status")).status == 200
    finally:
        await client.close()


def test_integration_is_copied_once_and_again_after_it_changes(tmp_path, monkeypatch):
    source = tmp_path / "source" / "cliproxy"
    (source / "translations").mkdir(parents=True)
    (source / "manifest.json").write_text('{"version": "1"}')
    (source / "translations" / "en.json").write_text("{}")
    target = tmp_path / "config" / "custom_components" / "cliproxy"
    monkeypatch.setattr(server, "INTEGRATION_SOURCE", source)
    monkeypatch.setattr(server, "INTEGRATION_TARGET", target)

    assert server.install_integration() is True
    assert (target / "translations" / "en.json").exists()
    assert server.install_integration() is False

    (source / "manifest.json").write_text('{"version": "2"}')
    assert server.install_integration() is True
    assert (target / "manifest.json").read_text() == '{"version": "2"}'


def test_an_empty_token_file_gets_a_new_token(tmp_path, monkeypatch):
    token_file = tmp_path / "api-token"
    token_file.write_text("")
    monkeypatch.setattr(server, "TOKEN_FILE", token_file)

    token = server.api_token()

    assert len(token) > 20
    assert token_file.read_text() == token
    assert server.api_token() == token


async def fake_supervisor(aiohttp_server, notify_statuses):
    calls = []
    statuses = iter(notify_statuses)

    async def notify(request):
        calls.append("notify")
        return web.json_response({}, status=next(statuses))

    async def discovery(request):
        calls.append(("discovery", (await request.json())["service"]))
        return web.json_response({"result": "ok"})

    app = web.Application()
    app.router.add_post(server.NOTIFY, notify)
    app.router.add_post("/discovery", discovery)
    return await aiohttp_server(app), calls


def addon_paths(tmp_path, monkeypatch, supervisor_url):
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / "manifest.json").write_text("{}")
    monkeypatch.setattr(server, "INTEGRATION_SOURCE", source)
    monkeypatch.setattr(server, "INTEGRATION_TARGET", tmp_path / "custom_components" / "cliproxy")
    monkeypatch.setattr(server, "RESTART_NOTICE_PENDING", tmp_path / "restart-notice-pending")
    monkeypatch.setattr(server, "SUPERVISOR", supervisor_url)
    monkeypatch.setattr(server, "ANNOUNCE_RETRY_SECONDS", 0)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    return {"options": {"url": "https://proxy.example", "management_key": "key"}, "token": "addon-token"}


async def test_the_restart_notice_is_retried_until_core_takes_it(aiohttp_server, tmp_path, monkeypatch):
    supervisor, calls = await fake_supervisor(aiohttp_server, notify_statuses=[502, 200])
    app = addon_paths(tmp_path, monkeypatch, str(supervisor.make_url("")).rstrip("/"))

    await server.on_startup(app)
    await asyncio.wait_for(app["announcer"], timeout=5)
    await app["cache"].session.close()

    assert (tmp_path / "custom_components" / "cliproxy" / "manifest.json").exists()
    assert calls == ["notify", ("discovery", "cliproxy"), "notify"]
    assert not (tmp_path / "restart-notice-pending").exists()


async def test_the_addon_keeps_announcing_while_the_supervisor_is_unreachable(tmp_path, monkeypatch):
    app = addon_paths(tmp_path, monkeypatch, "http://127.0.0.1:9")

    await server.on_startup(app)
    await asyncio.sleep(0.2)

    assert not app["announcer"].done()
    assert (tmp_path / "restart-notice-pending").exists()
    await server.on_cleanup(app)
