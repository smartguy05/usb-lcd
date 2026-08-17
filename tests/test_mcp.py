import json
import os
import subprocess
import sys

from usb_lcd_dashboard.mcp import INSTRUCTIONS, TOOLS, call_tool, handle
from usb_lcd_dashboard.todos import TodoStore


def result_text(result):
    return json.loads(result["content"][0]["text"])


def test_mcp_initializes_with_human_only_instructions(tmp_path):
    response = handle(TodoStore(tmp_path / "todos.sqlite3"), {
        "jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":"2025-06-18"}
    })
    assert response["result"]["protocolVersion"] == "2025-06-18"
    assert "human" in response["result"]["instructions"].lower()
    assert "never add your own" in INSTRUCTIONS.lower()
    assert {tool["name"] for tool in TOOLS} == {"list_todos", "add_todo", "update_todo", "complete_todo", "delete_todo"}


def test_mcp_tools_share_crud_state(tmp_path):
    store = TodoStore(tmp_path / "todos.sqlite3")
    created = result_text(call_tool(store, "add_todo", {"title":"Renew license", "priority":"high"}))
    item_id = created["todo"]["id"]
    assert result_text(call_tool(store, "list_todos", {}))["todos"][0]["id"] == item_id
    assert result_text(call_tool(store, "update_todo", {"id":item_id,"details":"Bring ID"}))["todo"]["details"] == "Bring ID"
    assert result_text(call_tool(store, "complete_todo", {"id":item_id}))["todo"]["status"] == "completed"
    error = handle(store, {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"delete_todo","arguments":{"id":item_id}}})
    assert error["result"]["isError"] is True
    assert result_text(call_tool(store, "delete_todo", {"id":item_id,"confirm":True}))["deleted"] is True


def test_stdio_server_exchanges_json_rpc_lines(tmp_path):
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(tmp_path)
    requests = "\n".join([
        json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}),
        json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}),
        json.dumps({"jsonrpc":"2.0","id":2,"method":"tools/list"}),
    ]) + "\n"
    result = subprocess.run(
        [sys.executable, "-m", "usb_lcd_dashboard", "mcp"], input=requests,
        text=True, capture_output=True, env=env, check=False, timeout=10,
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 0 and [reply["id"] for reply in replies] == [1, 2]
    assert len(replies[1]["result"]["tools"]) == 5
