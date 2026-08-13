# Runtime

The daemon process: its loop, its config, and how bytes reach the panel.

| Document | Covers |
| --- | --- |
| [daemon.md](daemon.md) | The loop, config hot-reload, sub-services, backoffs. |
| [config.md](config.md) | `Config`, TOML load/dump, **strict vs lenient loading**. |
| [transport.md](transport.md) | The IPC envelope, both socket transports, `poll_timeout`. |
| [display.md](display.md) | Dirty-rect diffing — what gets sent, and how little. |
| [device.md](device.md) | The `PanelDevice` protocol, serial, simulated, and the stub. |

## Where to start

Changing how often the panel updates → [transport.md](transport.md#poll_timeout-is-the-real-frame-rate-floor),
then [../architecture/frame-budget.md](../architecture/frame-budget.md).

Adding a config setting → [config.md](config.md#adding-a-setting). There are
four places, and a test that catches you missing one.

Supporting a new panel → [device.md](device.md). `make_device` and
`DISPLAY_KINDS` must both learn about it, or the config validates and then fails
at connect time.

Debugging "the panel went blank" → [display.md](display.md). The usual cause is
a silently reopened serial port, which `health_check` exists to catch.

## See also

- [../architecture/overview.md](../architecture/overview.md)
- [../rendering/README.md](../rendering/README.md) — what produces the frames this paints.
