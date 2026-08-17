from datetime import date

import pytest

from usb_lcd_dashboard.todos import TodoStore, rank_items


def test_todos_persist_update_complete_reopen_reorder_and_delete(tmp_path):
    path = tmp_path / "todos.sqlite3"
    store = TodoStore(path)
    first = store.create("First", "Details", "normal", "2026-08-20")
    second = store.create("Second", priority="high")
    assert [item.id for item in TodoStore(path).list()] == [first.id, second.id]
    assert store.update(first.id, title="Changed").title == "Changed"
    assert [item.id for item in store.reorder([second.id, first.id])] == [second.id, first.id]
    assert store.set_completed(second.id).status == "completed"
    assert [item.id for item in store.list()] == [first.id]
    assert store.set_completed(second.id, False).status == "open"
    store.delete(first.id)
    with pytest.raises(KeyError):
        store.get(first.id)


@pytest.mark.parametrize("field,value,match", [
    ("title", "", "required"),
    ("priority", "maximum", "one of"),
    ("due_date", "tomorrow", "YYYY-MM-DD"),
])
def test_todo_validation(tmp_path, field, value, match):
    store = TodoStore(tmp_path / "todos.sqlite3")
    values = {"title": "Valid", "priority": "normal", "due_date": None}
    values[field] = value
    with pytest.raises(ValueError, match=match):
        store.create(**values)


def test_rank_puts_overdue_and_near_due_before_priority(tmp_path):
    store = TodoStore(tmp_path / "todos.sqlite3")
    urgent = store.create("Urgent no date", priority="urgent")
    soon = store.create("Due soon", priority="low", due_date="2026-08-20")
    overdue = store.create("Late", due_date="2026-08-10")
    assert [item.id for item in rank_items([urgent, soon, overdue], date(2026, 8, 17))] == [overdue.id, soon.id, urgent.id]


def test_snapshot_is_cached_and_invalidated_by_writes(tmp_path):
    store = TodoStore(tmp_path / "todos.sqlite3")
    first = store.snapshot()
    store.create("New")
    second = store.snapshot()
    assert first.items == () and len(second.items) == 1
