import copy

import pytest
from homeassistant import config_entries
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.cliproxy import async_remove_config_entry_device
from custom_components.cliproxy.const import DOMAIN
from sample import AUTH_FILES, HISTORY, NOW
from usage import summarise

ADDON = "http://local-cliproxy:8099"
WORK = "aaaa000000000001"
HOME = "aaaa000000000002"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def reading(files=AUTH_FILES, history=HISTORY):
    return {**summarise(files, history, NOW), "proxy_url": "https://proxy.example"}


def serve(aioclient_mock, status):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{ADDON}/api/status", json=status)


def files_with(**cooldowns_by_index):
    files = copy.deepcopy(AUTH_FILES)
    for file in files["files"]:
        if file["auth_index"] in cooldowns_by_index:
            file["cooldowns"] = cooldowns_by_index[file["auth_index"]]
    return files


QUOTA_COOLDOWN = [{"scope": "credential", "reason": "credential_quota", "retry_at": "2026-11-09T00:00:00Z"}]


def home_reset_history():
    history = copy.deepcopy(HISTORY)
    limit = history["accounts"]["claude/home@example.com"][0]["limits"][0]
    limit.update(percent=0, severity="normal", resets_at="2026-11-15T17:00:00Z")
    return history


async def set_up(hass, aioclient_mock, status):
    serve(aioclient_mock, status)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"url": ADDON, "token": "addon-token"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def refresh(hass, entry, aioclient_mock, status):
    serve(aioclient_mock, status)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_addon_discovery_creates_the_entry(hass, aioclient_mock):
    serve(aioclient_mock, reading())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_HASSIO},
        data=HassioServiceInfo(
            config={"url": ADDON, "token": "addon-token"}, name="CLIProxy", slug="local_cliproxy", uuid="1234"
        ),
    )
    assert result["step_id"] == "hassio_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert result["data"] == {"url": ADDON, "token": "addon-token"}
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer addon-token"


async def test_rediscovery_moves_the_entry_to_the_new_addon(hass, aioclient_mock):
    entry = await set_up(hass, aioclient_mock, reading())
    moved = "http://f9820869-cliproxy:8099"
    aioclient_mock.get(f"{moved}/api/status", json=reading())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_HASSIO},
        data=HassioServiceInfo(
            config={"url": moved, "token": "new-token"}, name="CLIProxy", slug="f9820869_cliproxy", uuid="5678"
        ),
    )
    await hass.async_block_till_done()

    assert result["reason"] == "already_configured"
    assert dict(entry.data) == {"url": moved, "token": "new-token"}
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_only_devices_of_accounts_that_are_gone_can_be_removed(hass, aioclient_mock):
    entry = await set_up(hass, aioclient_mock, reading())
    devices = dr.async_get(hass)
    home = devices.async_get_device_by_identifier((DOMAIN, HOME), entry.entry_id)
    claude = devices.async_get_device_by_identifier((DOMAIN, "provider:claude"), entry.entry_id)
    files = copy.deepcopy(AUTH_FILES)
    files["files"] = [file for file in files["files"] if file["auth_index"] != HOME]
    await refresh(hass, entry, aioclient_mock, reading(files=files))

    assert await async_remove_config_entry_device(hass, entry, home) is True
    assert await async_remove_config_entry_device(hass, entry, claude) is False


async def test_adding_by_hand_points_to_the_addon(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == "abort"
    assert result["reason"] == "use_addon"


async def test_entities_show_usage_per_account_and_provider(hass, aioclient_mock):
    await set_up(hass, aioclient_mock, reading())

    assert hass.states.get("binary_sensor.claude_home_example_com_out_of_usage").state == "on"
    assert hass.states.get("binary_sensor.claude_work_example_com_out_of_usage").state == "off"
    assert hass.states.get("binary_sensor.claude_out_of_usage").state == "off"
    assert hass.states.get("sensor.claude_accounts_with_usage").state == "1"
    assert hass.states.get("sensor.claude_work_example_com_weekly_usage").state == "58.0"
    assert hass.states.get("sensor.claude_work_example_com_weekly_fable_usage").state == "28.0"
    assert hass.states.get("sensor.claude_home_example_com_usage_back").state == "2026-11-08T17:00:24+00:00"
    assert hass.states.get("sensor.codex_pro_example_com_next_reset").state == "2026-11-11T07:15:22+00:00"
    assert hass.states.get("sensor.codex_pro_example_com_credits").state == "61371.04"


async def test_changes_fire_automation_events(hass, aioclient_mock):
    entry = await set_up(hass, aioclient_mock, reading())
    out = async_capture_events(hass, "cliproxy_out_of_usage")
    restored = async_capture_events(hass, "cliproxy_usage_restored")
    resets = async_capture_events(hass, "cliproxy_usage_reset")

    await refresh(
        hass, entry, aioclient_mock, reading(files_with(**{WORK: QUOTA_COOLDOWN, HOME: []}), home_reset_history())
    )

    devices = dr.async_get(hass)
    work_device = devices.async_get_device_by_identifier((DOMAIN, WORK), entry.entry_id)
    home_device = devices.async_get_device_by_identifier((DOMAIN, HOME), entry.entry_id)
    assert [e.data for e in out] == [
        {
            "scope": "account",
            "account_id": WORK,
            "account": "claude/work@example.com",
            "provider": "claude",
            "usage_back_at": "2026-11-09T00:00:00+00:00",
            "device_id": work_device.id,
        }
    ]
    assert [(e.data["account"], e.data["device_id"]) for e in restored] == [("claude/home@example.com", home_device.id)]
    assert [
        (e.data["account"], e.data["limit"], e.data["previous_percent"], e.data["percent"], e.data["device_id"])
        for e in resets
    ] == [("claude/home@example.com", "weekly_all", 100.0, 0.0, home_device.id)]
    assert hass.states.get("binary_sensor.claude_out_of_usage").state == "off"

    await refresh(hass, entry, aioclient_mock, reading(files_with(**{WORK: QUOTA_COOLDOWN, HOME: QUOTA_COOLDOWN})))

    provider_device = devices.async_get_device_by_identifier((DOMAIN, "provider:claude"), entry.entry_id)
    assert [e.data for e in out[1:]] == [
        {
            "scope": "account",
            "account_id": HOME,
            "account": "claude/home@example.com",
            "provider": "claude",
            "usage_back_at": "2026-11-09T00:00:00+00:00",
            "device_id": home_device.id,
        },
        {"scope": "provider", "provider": "claude", "device_id": provider_device.id},
    ]
    assert hass.states.get("binary_sensor.claude_out_of_usage").state == "on"


async def test_device_triggers_run_automations(hass, aioclient_mock):
    entry = await set_up(hass, aioclient_mock, reading(files_with(**{HOME: []})))
    devices = dr.async_get(hass)
    provider_device = devices.async_get_device_by_identifier((DOMAIN, "provider:claude"), entry.entry_id)
    account_device = devices.async_get_device_by_identifier((DOMAIN, WORK), entry.entry_id)

    provider_triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, provider_device.id)
    account_triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, account_device.id)
    assert sorted(t["type"] for t in provider_triggers if t["domain"] == DOMAIN) == ["out_of_usage", "usage_restored"]
    assert sorted(t["type"] for t in account_triggers if t["domain"] == DOMAIN) == [
        "out_of_usage",
        "usage_reset",
        "usage_restored",
    ]

    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": provider_device.id,
                        "type": "out_of_usage",
                    },
                    "action": {"service": "test.automation", "data": {"what": "claude out"}},
                },
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": account_device.id,
                        "type": "usage_restored",
                    },
                    "action": {"service": "test.automation", "data": {"what": "work back"}},
                },
            ]
        },
    )

    await refresh(hass, entry, aioclient_mock, reading(files_with(**{WORK: QUOTA_COOLDOWN, HOME: QUOTA_COOLDOWN})))
    await refresh(hass, entry, aioclient_mock, reading(files_with(**{WORK: [], HOME: QUOTA_COOLDOWN})))

    assert [call.data["what"] for call in calls] == ["claude out", "work back"]


async def test_an_unreachable_addon_makes_entities_unavailable(hass, aioclient_mock):
    entry = await set_up(hass, aioclient_mock, reading())

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{ADDON}/api/status", status=502, json={"error": "CLIProxy request failed"})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.claude_out_of_usage").state == "unavailable"
