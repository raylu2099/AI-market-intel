# Multi-config support

Place named config files here as `<name>.env` to override the default `.env`.

Usage: `python -m intel.run --config friend china_open`

This loads `configs/friend.env` on top of the base `.env`, overriding any
matching keys. Use for different watchlists, timezones, Telegram targets, etc.
