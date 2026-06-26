"""To-do operations — a thin, testable layer over the SQLite todos table."""

from __future__ import annotations

from core.memory import Memory


class TodoManager:
    def __init__(self, memory: Memory):
        self.memory = memory

    def handle(self, action: str, task: str | None = None,
               task_id: int | None = None, priority: str = "medium") -> dict:
        if action == "add":
            if not task:
                return {"error": "A task description is required to add a todo."}
            return {"status": "added", "id": self.memory.add_todo(task, priority)}
        if action == "list":
            return {"todos": self.memory.list_todos()}
        if action == "complete":
            if task_id is None:
                return {"error": "task_id is required to complete a todo."}
            return {"completed": self.memory.complete_todo(int(task_id))}
        if action == "delete":
            if task_id is None:
                return {"error": "task_id is required to delete a todo."}
            return {"deleted": self.memory.delete_todo(int(task_id))}
        if action == "clear_completed":
            return {"cleared": self.memory.clear_completed_todos()}
        return {"error": f"Unknown todo action: {action}"}
