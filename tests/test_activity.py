import pytest

from usb_lcd_dashboard.activity import describe_activity


@pytest.mark.parametrize(
    "tool,tool_input,expected",
    [
        ("Read", {"file_path": "/work/widget/main.py"}, "Reading main.py"),
        ("Read", {}, "Reading file"),
        ("Write", {"file_path": "/work/widget/src/app.py"}, "Writing src/app.py"),
        ("Edit", {"file_path": "/work/widget/src/app.py"}, "Editing src/app.py"),
        ("Glob", {"pattern": "**/*.py"}, "Finding **/*.py"),
        ("Grep", {"pattern": "render_dashboard"}, "Searching for render_dashboard"),
        ("Bash", {"command": "pytest -q", "description": "Run tests"}, "Running Run tests"),
        ("Bash", {"command": "pytest -q"}, "Running pytest -q"),
        ("WebFetch", {"url": "https://example.com"}, "Fetching https://example.com"),
        ("WebSearch", {"query": "turing lcd"}, "Searching for turing lcd"),
        ("Task", {"description": "Audit the installer"}, "Audit the installer"),
        ("Task", {}, "Running task"),
        # Codex and MCP tools have no known schema; use whatever they provide.
        ("exec_command", {"command": ["ls", "-l"]}, "Running ls -l"),
        ("apply_patch", {"path": "/work/widget/src/app.py"}, "Working on src/app.py"),
        ("mystery_tool", {}, "mystery_tool"),
        ("", {}, ""),
    ],
)
def test_descriptions_match_the_agent_status_line(tool, tool_input, expected):
    assert describe_activity(tool, tool_input, "/work/widget") == expected


def test_paths_outside_the_session_directory_are_kept_absolute():
    assert describe_activity("Read", {"file_path": "/etc/hosts"}, "/work/widget") == (
        "Reading /etc/hosts"
    )


def test_long_descriptions_are_truncated():
    activity = describe_activity("Bash", {"description": "x" * 200}, "")
    assert activity.endswith("…")
    assert len(activity) <= len("Running ") + 50


def test_non_dict_tool_input_is_tolerated():
    assert describe_activity("Read", None) == "Reading file"
    assert describe_activity("Read", "junk") == "Reading file"
