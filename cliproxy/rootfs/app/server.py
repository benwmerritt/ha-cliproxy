"""CLIProxy add-on: the side-menu panel and the status API the integration reads."""

from __future__ import annotations

import asyncio
import filecmp
import hmac
import json
import logging
import os
import secrets
import shutil
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import aiohttp
from aiohttp import web

from usage import fetch_status, open_session

PORT = 8099
INGRESS_PEER = "172.30.32.2"
CACHE_SECONDS = 20
OPTIONS = Path("/data/options.json")
TOKEN_FILE = Path("/data/api-token")
PANEL = Path(__file__).parent / "panel" / "index.html"
INTEGRATION_SOURCE = Path("/integration/cliproxy")
INTEGRATION_TARGET = Path("/homeassistant/custom_components/cliproxy")
SUPERVISOR = "http://supervisor"

log = logging.getLogger("cliproxy")


class StatusCache:
    def __init__(self, options: dict) -> None:
        self.url = options["url"].rstrip("/")
        self.management_key = options["management_key"]
        self.session = open_session(self.url, options.get("connect_address") or None)
        self.lock = asyncio.Lock()
        self.value: dict | None = None
        self.fetched = 0.0

    async def get(self) -> dict:
        async with self.lock:
            if self.value is None or time.monotonic() - self.fetched > CACHE_SECONDS:
                status = await fetch_status(self.session, self.url, self.management_key, datetime.now(UTC))
                self.value = {**status, "proxy_url": self.url}
                self.fetched = time.monotonic()
            return self.value


def api_token() -> str:
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(32))
        TOKEN_FILE.chmod(0o600)
    return TOKEN_FILE.read_text().strip()


@web.middleware
async def require_ingress_or_token(request: web.Request, handler):
    if request.remote == INGRESS_PEER:
        return await handler(request)
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if hmac.compare_digest(supplied.encode(), request.app["token"].encode()):
        return await handler(request)
    raise web.HTTPUnauthorized()


async def panel(_: web.Request) -> web.FileResponse:
    return web.FileResponse(PANEL, headers={"Cache-Control": "no-store"})


async def status(request: web.Request) -> web.Response:
    try:
        return web.json_response(await request.app["cache"].get())
    except (aiohttp.ClientError, TimeoutError) as error:
        log.warning("CLIProxy request failed: %s", error)
        return web.json_response({"error": f"CLIProxy request failed: {error}"}, status=502)


def install_integration() -> bool:
    if INTEGRATION_TARGET.exists() and not tree_differs(INTEGRATION_SOURCE, INTEGRATION_TARGET):
        return False
    shutil.rmtree(INTEGRATION_TARGET, ignore_errors=True)
    shutil.copytree(INTEGRATION_SOURCE, INTEGRATION_TARGET, ignore=shutil.ignore_patterns("__pycache__"))
    return True


def tree_differs(source: Path, target: Path) -> bool:
    comparison = filecmp.dircmp(source, target, ignore=["__pycache__"])
    if comparison.left_only or comparison.right_only or comparison.funny_files:
        return True
    _, mismatch, errors = filecmp.cmpfiles(source, target, comparison.common_files, shallow=False)
    if mismatch or errors:
        return True
    return any(tree_differs(source / name, target / name) for name in comparison.common_dirs)


async def supervisor(session: aiohttp.ClientSession, method: str, path: str, body: dict) -> None:
    headers = {"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}"}
    async with session.request(method, f"{SUPERVISOR}{path}", json=body, headers=headers) as response:
        if response.status >= 400:
            log.warning("Supervisor %s %s returned %s: %s", method, path, response.status, await response.text())


async def announce(app: web.Application) -> None:
    async with aiohttp.ClientSession() as session:
        if install_integration():
            log.info("Installed the CLIProxy integration into custom_components")
            await supervisor(
                session,
                "POST",
                "/core/api/services/persistent_notification/create",
                {
                    "notification_id": "cliproxy_integration_installed",
                    "title": "CLIProxy integration installed",
                    "message": "Restart Home Assistant to load the CLIProxy integration. It is then discovered under Settings → Devices & services.",
                },
            )
        await supervisor(
            session,
            "POST",
            "/discovery",
            {"service": "cliproxy", "config": {"url": f"http://{socket.gethostname()}:{PORT}", "token": app["token"]}},
        )


async def on_startup(app: web.Application) -> None:
    app["cache"] = StatusCache(app["options"])
    try:
        await announce(app)
    except (aiohttp.ClientError, OSError) as error:
        log.warning("Could not install or announce the integration: %s", error)


async def on_cleanup(app: web.Application) -> None:
    await app["cache"].session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = web.Application(middlewares=[require_ingress_or_token])
    app["options"] = json.loads(OPTIONS.read_text())
    app["token"] = api_token()
    app.router.add_get("/", panel)
    app.router.add_get("/api/status", status)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    web.run_app(app, port=PORT, access_log=None)


if __name__ == "__main__":
    main()
