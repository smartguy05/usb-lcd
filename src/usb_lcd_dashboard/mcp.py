"""Dependency-free stdio MCP server for the user's human todo list."""

from __future__ import annotations

import json
import sys
from typing import Any

from . import __version__
from .todos import PRIORITIES, TodoStore

INSTRUCTIONS = (
    "This is the human user's personal action list, not agent memory or a work plan. "
    "Use it only for concrete actions the user needs to take. You may add such an item "
    "when context makes it useful, but list first and avoid duplicates. Update or complete "
    "items only when context supports the change. Permanently delete only when the user "
    "explicitly requests deletion. Never add your own implementation steps or scratch work."
)


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


_ID = {"type": "string", "description": "Stable todo UUID returned by list_todos"}
_FIELDS = {
    "title": {"type": "string", "maxLength": 240},
    "details": {"type": "string", "maxLength": 4000},
    "priority": {"type": "string", "enum": list(PRIORITIES)},
    "due_date": {"type": ["string", "null"], "description": "Date as YYYY-MM-DD, or null"},
}

TOOLS = [
    {
        "name": "list_todos",
        "description": "List the human user's action items. Call before adding to avoid duplicates.",
        "inputSchema": _object({"include_completed": {"type": "boolean", "default": False}}),
    },
    {
        "name": "add_todo",
        "description": "Add a concrete action the human user needs to take; never add agent work steps.",
        "inputSchema": _object(dict(_FIELDS), ["title"]),
    },
    {
        "name": "update_todo",
        "description": "Edit fields or manual position of an existing human todo.",
        "inputSchema": _object({"id": _ID, **_FIELDS, "position": {"type": "integer", "minimum": 0}}, ["id"]),
    },
    {
        "name": "complete_todo",
        "description": "Mark a human todo completed, or reopen it with completed=false.",
        "inputSchema": _object({"id": _ID, "completed": {"type": "boolean", "default": True}}, ["id"]),
    },
    {
        "name": "delete_todo",
        "description": "Permanently delete only when the user explicitly requested deletion; confirm must be true.",
        "inputSchema": _object({"id": _ID, "confirm": {"type": "boolean", "description": "Must be true"}}, ["id", "confirm"]),
    },
]


def _payload(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, indent=2)}],
        "isError": is_error,
    }


def call_tool(store: TodoStore, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_todos":
        items = store.list(bool(arguments.get("include_completed", False)))
        return _payload({"todos": [item.to_json() for item in items]})
    if name == "add_todo":
        item = store.create(
            arguments.get("title"), arguments.get("details", ""),
            arguments.get("priority", "normal"), arguments.get("due_date"),
        )
        return _payload({"todo": item.to_json()})
    if name == "update_todo":
        item_id = str(arguments.get("id") or "")
        changes = {key: value for key, value in arguments.items() if key in _FIELDS}
        item = store.update(item_id, **changes)
        if "position" in arguments:
            if item.status != "open":
                raise ValueError("only open todos can be reordered")
            open_items = store.list()
            ids = [item.id for item in open_items if item.id != item_id]
            position = max(0, min(int(arguments["position"]), len(ids)))
            ids.insert(position, item_id)
            store.reorder(ids)
            item = store.get(item_id)
        return _payload({"todo": item.to_json()})
    if name == "complete_todo":
        item = store.set_completed(str(arguments.get("id") or ""), bool(arguments.get("completed", True)))
        return _payload({"todo": item.to_json()})
    if name == "delete_todo":
        if arguments.get("confirm") is not True:
            raise ValueError("permanent deletion requires confirm=true")
        item_id = str(arguments.get("id") or "")
        store.delete(item_id)
        return _payload({"deleted": True, "id": item_id})
    raise ValueError(f"unknown tool: {name}")


def handle(store: TodoStore, request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    if request_id is None:
        return None
    try:
        if method == "initialize":
            requested = (request.get("params") or {}).get("protocolVersion") or "2025-06-18"
            result = {
                "protocolVersion": requested,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "usb-lcd-dashboard-todos", "version": __version__},
                "instructions": INSTRUCTIONS,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            result = call_tool(store, str(params.get("name") or ""), arguments)
        else:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except (KeyError, ValueError, TypeError) as exc:
        return {"jsonrpc": "2.0", "id": request_id, "result": _payload({"error": str(exc)}, is_error=True)}
    except Exception:
        return {"jsonrpc": "2.0", "id": request_id, "result": _payload({"error": "todo storage failed"}, is_error=True)}


def serve(store: TodoStore | None = None) -> int:
    repository = store or TodoStore()
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = handle(repository, request)
        except (json.JSONDecodeError, ValueError) as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0
