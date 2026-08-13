# Admin surfaces

The two optional things the daemon starts alongside the panel. Neither may take
the panel down; both log and carry on if they fail to start.

| Document | Covers |
| --- | --- |
| [settings-editor.md](settings-editor.md) | The loopback HTTP editor, its routes, and its security model. |
| [tray.md](tray.md) | The Windows notification-area icon. |

## The most useful thing here for an agent

```bash
curl -s -o frame.png http://127.0.0.1:45723/api/preview.png
```

That is the frame **actually on the panel** right now, taken from a running
daemon, with no hardware needed. `GET /api/config` and `GET /api/widgets` give
you the live config and the widget registry as JSON. See
[settings-editor.md](settings-editor.md#routes).

## See also

- [../runtime/daemon.md](../runtime/daemon.md) — which starts both, best-effort.
- [../rendering/widgets.md](../rendering/widgets.md) — the registry the editor's form generates itself from.
