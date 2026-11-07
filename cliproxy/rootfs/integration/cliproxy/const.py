"""Constants for the CLIProxy integration."""

from datetime import timedelta

DOMAIN = "cliproxy"
SCAN_INTERVAL = timedelta(seconds=60)

EVENT_OUT_OF_USAGE = "cliproxy_out_of_usage"
EVENT_USAGE_RESTORED = "cliproxy_usage_restored"
EVENT_USAGE_RESET = "cliproxy_usage_reset"

PROVIDER_PREFIX = "provider:"
