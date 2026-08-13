# transport.py — the IPC wire

> **Covers:** `src/usb_lcd_dashboard/transport.py`

Owns the envelope format and the two socket transports that carry events from a
hook process into the daemon. It owns framing and non-blocking send semantics;
it owns nothing about what an event *means* — that is
[normalize.py](../sessions/normalize.md).

## API

| Symbol | Line | Purpose |
| --- | --- | --- |
| `MAX_WIRE_BYTES = 65_535` | `transport.py:10` | Receive buffer cap. |
| `send_event(config, provider, payload) -> bool` | `transport.py:47` | Wrap a payload and send it. Returns success. |
| `send_control(config, control) -> bool` | `transport.py:51` | Send a control message, e.g. `shutdown`. |
| `bind_socket(config) -> socket.socket` | `transport.py:58` | The daemon's listener. |
| `poll_timeout(config) -> float` | `transport.py:76` | `min(0.2, config.frame_interval)`. |
| `receive_event(server, config) -> bytes` | `transport.py:88` | Read one event's raw bytes. |

## The envelope

Both are plain JSON, versioned:

```json
{"schema_version": 1, "provider": "claude", "payload": { ... }}
{"schema_version": 1, "control": "shutdown"}
```

Built in `_wire_data` (`transport.py:14-18`). The daemon ignores any envelope
whose `schema_version` is not 1 (`daemon.py:166`).

## Two transports

| `ipc_mode` | Family | Type | Address |
| --- | --- | --- | --- |
| `unix` (POSIX default) | `AF_UNIX` | `SOCK_DGRAM` | `runtime_dir()/usb-lcd-dashboard.sock` |
| `tcp` (Windows default) | `AF_INET` | `SOCK_STREAM` | `127.0.0.1:45722` |

Unix mode is datagram, so one packet is one event and `receive_event` is a
single `recv()` (`transport.py:90`). TCP mode accepts a connection and
accumulates chunks with a 0.1 s per-chunk timeout, stopping on timeout, an empty
chunk, or `MAX_WIRE_BYTES` (`transport.py:92-104`).

The Unix socket is created with a `0o700` parent, a stale socket is unlinked
first, and the socket is chmodded `0o600` (`transport.py:65-71`) — it stays
private to the owning user.

## `poll_timeout` is the real frame-rate floor

Quoted from `transport.py:76-85`:

> This is the real floor on the frame rate: the loop blocks here, then sleeps
> the remainder of the frame, so a fixed 0.2s timeout capped the panel at 5Hz
> however high refresh_hz was set.

The daemon blocks in `receive_event` for up to this long, then sleeps
`frame_interval - timeout`. A hardcoded 0.2 s therefore made `refresh_hz` above
5 meaningless. Tying it to the frame interval lets an animated widget reach its
configured rate, while a slow panel keeps the old 0.2 s responsiveness to an
incoming event. `tests/test_transport.py::test_the_poll_timeout_follows_the_frame_rate`
pins it.

## A hook must never crash because the daemon is down

`_send` gives the client socket a 0.1 s timeout and swallows every `OSError`,
returning `False` (`transport.py:29`, `41-42`). Connection refused, no listener,
timeout — all the same: the hook exits 0 and the terminal is undisturbed. This
is the same principle as lenient config loading; see
[../architecture/invariants.md](../architecture/invariants.md).

Payloads over 60,000 bytes are refused before any socket work
(`transport.py:23-24`), leaving headroom under the receiver's 65,535 cap.

## Tests

`tests/test_transport.py` — a missing daemon is non-blocking on both transports,
a TCP round trip works, the status-line proxy preserves downstream output, and
`poll_timeout` tracks `frame_interval`.

## See also

- [daemon.md](daemon.md) — the loop that calls all of this.
- [config.md](config.md) — `ipc_mode`, `ipc_port`, `frame_interval`.
- [../integration/cli.md](../integration/cli.md) — `emit` and `statusline-proxy`, the senders.
