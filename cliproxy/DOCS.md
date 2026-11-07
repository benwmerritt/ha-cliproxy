# CLIProxy

This add-on shows your CLIProxy accounts in the sidebar and installs the CLIProxy integration, which turns their usage into entities and automation triggers.

## Configuration

- **CLIProxy URL.** The proxy's base URL, such as `https://cliproxy.example.ts.net`.
- **Management key.** CLIProxy's `remote-management` secret. Only this add-on holds it.
- **Connect address.** Optional. An IP address to connect to instead of looking the hostname up. Home Assistant OS can't resolve tailnet `*.ts.net` names, so give the proxy's tailnet IP here. TLS still uses the hostname from the URL.

## After the first start

The add-on copies the integration into `custom_components/cliproxy` and posts a notification. Restart Home Assistant, then add CLIProxy from **Settings → Devices & services**, where it shows as discovered.

The [README](https://github.com/benwmerritt/ha-cliproxy#readme) lists the entities, events and device triggers, with example automations.

## Troubleshooting

The panel shows the error CLIProxy returned. A 401 means the management key is wrong. A connection error usually means Home Assistant can't reach the proxy: check the URL, and set the connect address for a tailnet URL.
