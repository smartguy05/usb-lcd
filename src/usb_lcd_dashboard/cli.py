from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import subprocess
import sys

from .config import NO_WINDOW, config_home, load_config
from .daemon import DashboardDaemon
from .doctor import paint_test, print_report
from .install import install, uninstall
from .transport import send_control, send_event


def _json_stdin() -> tuple[bytes, dict]:
    raw = sys.stdin.buffer.read()
    try:
        return raw, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return raw, {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="usb-lcd-dashboard")
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--simulate", action="store_true")
    emit = sub.add_parser("emit")
    emit.add_argument("--provider", choices=["claude", "codex"], required=True)
    proxy = sub.add_parser("statusline-proxy")
    proxy.add_argument("--downstream-b64", default="")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--paint-test", action="store_true")
    sub.add_parser("install")
    sub.add_parser("uninstall")
    sub.add_parser("shutdown")
    sub.add_parser("mcp")
    args = parser.parse_args(argv)

    log_options = {}
    if os.name == "nt" and args.command == "run":
        log_dir = config_home() / "usb-lcd-dashboard"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_options["filename"] = str(log_dir / "dashboard.log")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        **log_options,
    )
    # The todo MCP server is a standalone local tool. A broken display or IPC
    # setting must not prevent the user or an agent from managing the list.
    if args.command == "mcp":
        from .mcp import serve

        return serve()
    # Only the commands that put pixels on the panel need a layout they can
    # actually draw. A hook needs the IPC address and nothing else, and
    # install/uninstall need the paths — so a bad tile rect must not fail them.
    # It used to: one unknown widget name in config.toml made every hook in
    # every Claude and Codex session exit with a traceback, and blocked the one
    # command that could put the file right again.
    # `doctor` is lenient too, and reports the bad layout as a failed check —
    # crashing would be a poor answer from the command you run to find out
    # what is wrong.
    config = load_config(strict=args.command == "run")

    if args.command == "run":
        DashboardDaemon(config, simulate=args.simulate).run()
        return 0
    if args.command == "emit":
        _raw, payload = _json_stdin()
        send_event(config, args.provider, payload)
        return 0
    if args.command == "statusline-proxy":
        raw, payload = _json_stdin()
        send_event(config, "claude", payload)
        if args.downstream_b64:
            try:
                downstream = base64.urlsafe_b64decode(args.downstream_b64).decode()
            except (ValueError, UnicodeDecodeError):
                downstream = ""
            if downstream:
                result = subprocess.run(
                    downstream,
                    shell=True,
                    input=raw,
                    stdout=sys.stdout.buffer,
                    stderr=sys.stderr.buffer,
                    check=False,
                    creationflags=NO_WINDOW,
                )
                return result.returncode
        return 0
    if args.command == "doctor":
        ok = print_report(config)
        if args.paint_test:
            paint_test(config)
            print("OK    paint test         frame sent to LCD")
        return 0 if ok else 1
    if args.command == "install":
        install()
        return 0
    if args.command == "uninstall":
        uninstall()
        return 0
    if args.command == "shutdown":
        return 0 if send_control(config, "shutdown") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

