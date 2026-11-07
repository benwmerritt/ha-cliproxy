# CLIProxy for Home Assistant

A Home Assistant add-on and integration for [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI), the proxy that pools Claude, Codex and other subscription accounts behind one API.

The add-on puts a CLIProxy page in the sidebar. It lists every account with its usage limits, when each resets and any quota cooldown. The integration turns the same data into entities, events and device triggers, so automations can act when an account runs out or comes back.

The usage numbers come from the quota history in [benwmerritt/CLIProxyAPI](https://github.com/benwmerritt/CLIProxyAPI). Upstream CLIProxyAPI has no quota history, so on upstream every account shows as having usage unless CLIProxy has put it in a quota cooldown.

## Install

1. In Home Assistant, open **Settings → Add-ons → Add-on store**, then **⋮ → Repositories**, and add `https://github.com/benwmerritt/ha-cliproxy`.
2. Install **CLIProxy** and fill in its configuration:
   - **CLIProxy URL**, such as `https://cliproxy.example.ts.net`.
   - **Management key**, CLIProxy's `remote-management` secret.
   - **Connect address**, only when Home Assistant can't resolve the URL's hostname. Home Assistant OS can't resolve tailnet `*.ts.net` names even with the Tailscale add-on, so put the proxy's tailnet IP here. The add-on connects to that IP and still sends the hostname for TLS, which Tailscale Serve needs.
3. Start the add-on. On first start it copies the integration into `custom_components/cliproxy` and posts a notification asking you to restart Home Assistant.
4. Restart Home Assistant. **Settings → Devices & services** then shows CLIProxy as discovered. Add it.

Updating the add-on updates the integration too. Restart Home Assistant when the notification asks.

## What you get

Each provider (Claude, Codex, ...) and each account is a device. The account devices sit under their provider.

| Entity | On | What it shows |
| --- | --- | --- |
| `binary_sensor.<account>_out_of_usage` | account | On while CLIProxy can't use the account: a quota cooldown, or an active limit at 100% with no credits left. Attribute `usage_back_at`. |
| `binary_sensor.<provider>_out_of_usage` | provider | On when every account of that provider is out of usage. |
| `sensor.<account>_<limit>_usage` | account | Percent used of one limit, such as `weekly_usage` or `weekly_fable_usage`. Attribute `resets_at`. |
| `sensor.<account>_next_reset` | account | When the next limit resets. A timestamp, so it works with a time trigger. |
| `sensor.<account>_usage_back` | account | When an account that's out of usage can be used again. Unknown while it has usage. |
| `sensor.<account>_credits` | account | Codex usage credits, for accounts that have them. |
| `sensor.<account>_status` | account | CLIProxy's status for the account, with its message. Diagnostic. |
| `sensor.<provider>_accounts_with_usage` | provider | How many of the provider's accounts have usage left. |

The integration polls the add-on every minute, and the add-on reads CLIProxy at most every 20 seconds.

## Automations

The integration fires three events. Each carries `device_id`, `scope` (`account` or `provider`) and `provider`. Account events also carry `account` and `account_id`.

| Event | When | Extra data |
| --- | --- | --- |
| `cliproxy_out_of_usage` | An account, or a whole provider, runs out | `usage_back_at` for accounts |
| `cliproxy_usage_restored` | An account or provider that was out has usage again | |
| `cliproxy_usage_reset` | An account's limit starts a new window | `limit`, `limit_name`, `previous_percent`, `percent`, `resets_at` |

The same three show up as device triggers in the automation editor: **Ran out of usage**, **Usage came back** and **Usage limit reset**. Provider devices offer the first two.

Ping your phone and play a song when Claude usage comes back:

```yaml
triggers:
  - trigger: event
    event_type: cliproxy_usage_restored
    event_data:
      scope: provider
      provider: claude
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Claude is back
      message: An account has usage again.
      data:
        push:
          sound:
            name: default
            critical: 1
            volume: 1.0
  - action: music_assistant.play_media
    target:
      entity_id: media_player.office_speaker
    data:
      media_id: Major Bag Alert
      media_type: track
```

Tell you when an account runs out, and when it's due back:

```yaml
triggers:
  - trigger: event
    event_type: cliproxy_out_of_usage
    event_data:
      scope: account
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: >-
        {{ trigger.event.data.account }} is out of usage until
        {{ as_timestamp(trigger.event.data.usage_back_at) | timestamp_custom('%a %-I:%M %p') }}.
```

## How it fits together

```text
CLIProxy management API ──► add-on ──► sidebar panel (through Home Assistant ingress)
                                  └──► /api/status ──► integration ──► entities, events, device triggers
```

Only the add-on holds the management key, and it reads only two endpoints: `auth-files` and `quota-history`. It strips tokens and file paths before passing anything on. The integration reaches the add-on with a random token that the add-on hands over through Supervisor discovery. The panel is reachable only through Home Assistant's ingress, so only Home Assistant admins see it.

## Development

```sh
uv sync
uv run pytest -p no:homeassistant tests/addon   # add-on, with real sockets
uv run pytest tests/integration                  # integration, on Home Assistant's test harness
uv run ruff check . && uv run ruff format --check .
```

The integration's source is `cliproxy/rootfs/integration/cliproxy`, inside the add-on, because the add-on installs it. `custom_components` at the root links there for the tests.
