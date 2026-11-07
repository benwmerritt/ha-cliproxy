"""Config flow for CLIProxy: set up from the add-on's discovery."""

from __future__ import annotations

from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN
from .coordinator import fetch_status


class CLIProxyConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="use_addon")

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._discovered = {"url": discovery_info.config["url"], "token": discovery_info.config["token"]}
        self._abort_if_unique_id_configured(updates=self._discovered)
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await fetch_status(async_get_clientsession(self.hass), **self._discovered)
            except (aiohttp.ClientError, TimeoutError, ValueError, UpdateFailed):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="CLIProxy", data=self._discovered)
        return self.async_show_form(step_id="hassio_confirm", errors=errors)
