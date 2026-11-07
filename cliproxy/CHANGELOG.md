# Changelog

## 0.1.2

- Only account-wide limits put an account out of usage. A full model or Codex code-review limit no longer does.
- A limit whose reset time has passed reads 0%, and the reset event fires when that time passes, even without a new reading from CLIProxy.
- Codex code-review and per-model limits get their own sensors and window names.
- The integration picks up a new add-on address or token when the add-on is reinstalled or moved.
- Removed accounts' devices can be deleted.
- The panel shows a Codex account running on credits as **Using credits**, and shows provider errors as plain messages.
- The restart notice is retried until Home Assistant receives it, and the add-on keeps serving when Supervisor is unreachable.

## 0.1.1

- Run the server as the container entrypoint, so it keeps the Supervisor token and can announce itself.

## 0.1.0

- Sidebar panel with each CLIProxy account's usage limits, reset times and cooldowns.
- Installs the CLIProxy integration and announces itself so Home Assistant discovers it.
