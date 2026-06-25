"""Tool dispatch: permission-gate, execute, audit-log, and stringify results.

`execute_tool` is the single entry point the agent loop calls for every
tool_use block. It is synchronous (subprocess / sqlite / network) and is
expected to be run in a worker thread by the async agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from config import Settings
from core.memory import Memory
from core.permissions import PermissionManager, Risk
from modules.filesystem import reader, writer
from modules.system import apps, clipboard, shell, sysinfo
from modules.web import download, scraper, search

MAX_RESULT_CHARS = 10_000

# Tools whose backend handler arrives in a later phase.
NOT_YET_IMPLEMENTED = {
    "take_screenshot": "Screenshots arrive in Phase 6.",
    "set_reminder": "Reminders arrive in Phase 6.",
    "read_email": "Email arrives in Phase 7.",
    "send_email": "Email arrives in Phase 7.",
}


@dataclass
class ToolContext:
    settings: Settings
    memory: Memory
    permissions: PermissionManager


def _stringify(obj) -> str:
    if isinstance(obj, str):
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n...[result truncated]"
    return text


def _preview(tool_name: str, ti: dict) -> str:
    if tool_name == "run_shell_command":
        return (f"Shell: {ti.get('shell', 'powershell')}\n"
                f"Command:\n  {ti.get('command', '')}\n"
                f"Working dir: {ti.get('working_directory') or '(current)'}")
    if tool_name == "write_file":
        content = str(ti.get("content", ""))
        return (f"{ti.get('mode', 'write').upper()} file: {ti.get('file_path')}\n"
                f"Size: {len(content)} chars\n"
                f"Preview:\n  {content[:300]}")
    if tool_name == "move_or_copy_file":
        return (f"{ti.get('operation', '?').upper()}\n"
                f"  from: {ti.get('source_path')}\n"
                f"  to:   {ti.get('destination_path')}\n"
                f"  overwrite: {ti.get('overwrite', False)}")
    if tool_name == "delete_file":
        dest = "Recycle Bin" if ti.get("send_to_recycle_bin", True) else "PERMANENT"
        return f"Delete ({dest}): {ti.get('path')}"
    if tool_name == "download_file":
        return f"Download:\n  {ti.get('url')}\n  -> {ti.get('save_path')}"
    if tool_name == "open_application":
        return f"Open application: {ti.get('app_name')} {ti.get('arguments', '')}".strip()
    if tool_name == "clipboard_write":
        content = str(ti.get("content", ""))
        return f"Write to clipboard ({len(content)} chars):\n  {content[:200]}"
    if tool_name == "remember_fact":
        return f"Remember [{ti.get('category', 'other')}]: {ti.get('fact')}"
    return json.dumps(ti, ensure_ascii=False)


def execute_tool(tool_name: str, tool_input: dict, ctx: ToolContext) -> str:
    """Permission-check, run, and audit a single tool call. Returns a string."""
    ti = tool_input or {}

    if tool_name in NOT_YET_IMPLEMENTED:
        return f"[not available] {NOT_YET_IMPLEMENTED[tool_name]}"

    preview = _preview(tool_name, ti)
    decision = ctx.permissions.check(tool_name, ti, preview=preview)

    if not decision.allowed:
        ctx.memory.log_audit(tool_name, ti, approved_by="blocked", result="denied")
        return f"[blocked] {decision.reason}"

    if decision.needs_approval:
        approved = ctx.permissions.request_approval(tool_name, decision.risk, preview)
        if not approved:
            ctx.memory.log_audit(tool_name, ti, approved_by="user", result="denied")
            return "[denied] The user declined this action."

    try:
        result = _run(tool_name, ti, ctx)
        approver = "auto" if not decision.needs_approval else "user"
        ctx.memory.log_audit(tool_name, ti, approved_by=approver, result="success")
        return _stringify(result)
    except Exception as e:
        ctx.memory.log_audit(tool_name, ti, approved_by="auto", result="failure")
        return f"[error] {tool_name} failed: {e}"


def _run(tool_name: str, ti: dict, ctx: ToolContext):
    # ----- system -----
    if tool_name == "run_shell_command":
        return shell.run_shell_command(
            command=ti["command"],
            shell=ti.get("shell", "powershell"),
            working_directory=ti.get("working_directory"),
            timeout_seconds=ti.get("timeout_seconds", 30),
        )
    if tool_name == "get_system_info":
        return sysinfo.get_system_info(ti.get("info_type", "all"))
    if tool_name == "open_application":
        return apps.open_application(ti["app_name"], ti.get("arguments", ""))
    if tool_name == "clipboard_read":
        return {"clipboard": clipboard.clipboard_read()}
    if tool_name == "clipboard_write":
        clipboard.clipboard_write(ti["content"])
        return {"status": "copied to clipboard"}

    # ----- filesystem (reads) -----
    if tool_name == "read_file":
        if ctx.permissions.is_path_blocked(ti["file_path"]):
            return {"error": "Path is in a blocked directory."}
        return reader.read_file(ti["file_path"], ti.get("encoding", "utf-8"),
                                ti.get("max_chars", 50_000))
    if tool_name == "list_directory":
        if ctx.permissions.is_path_blocked(ti["directory_path"]):
            return {"error": "Path is in a blocked directory."}
        return reader.list_directory(
            ti["directory_path"], ti.get("recursive", False),
            ti.get("include_hidden", False), ti.get("filter_extension"))
    if tool_name == "search_files":
        return reader.search_files(ti["search_path"], ti["pattern"],
                                   ti.get("search_type", "filename"),
                                   ti.get("recursive", True))

    # ----- filesystem (writes) -----
    if tool_name == "write_file":
        return writer.write_file(ti["file_path"], ti["content"],
                                 ti.get("mode", "write"),
                                 ti.get("encoding", "utf-8"))
    if tool_name == "move_or_copy_file":
        return writer.move_or_copy_file(ti["source_path"], ti["destination_path"],
                                        ti["operation"], ti.get("overwrite", False))
    if tool_name == "delete_file":
        return writer.delete_file(ti["path"], ti.get("send_to_recycle_bin", True))

    # ----- web -----
    if tool_name == "web_search":
        if not ctx.settings.web_search_enabled:
            return {"error": "Web search is disabled in settings."}
        n = ti.get("max_results", ctx.settings.max_search_results)
        return {"results": search.web_search(ti["query"], n)}
    if tool_name == "scrape_webpage":
        if not ctx.settings.scraping_enabled:
            return {"error": "Scraping is disabled in settings."}
        return scraper.scrape_webpage(ti["url"], ti.get("extract_mode", "text"),
                                      ti.get("wait_for_js", False))
    if tool_name == "download_file":
        save_path = ti["save_path"]
        if ctx.permissions.is_path_blocked(save_path):
            return {"error": "Save path is in a blocked directory."}
        if ctx.settings.allowed_directories and not ctx.permissions.is_path_allowed(save_path):
            return {"error": "Save path is outside ALLOWED_DIRECTORIES."}
        return download.download_file(ti["url"], save_path)

    # ----- memory -----
    if tool_name == "remember_fact":
        fid = ctx.memory.add_fact(ti["fact"], ti.get("category", "other"))
        return {"status": "remembered", "id": fid}
    if tool_name == "recall_memory":
        return {"facts": ctx.memory.recall_facts(ti["query"])}

    # ----- todos -----
    if tool_name == "manage_todo":
        return _manage_todo(ti, ctx)

    return {"error": f"No handler for tool '{tool_name}'."}


def _manage_todo(ti: dict, ctx: ToolContext):
    action = ti.get("action")
    m = ctx.memory
    if action == "add":
        tid = m.add_todo(ti["task"], ti.get("priority", "medium"))
        return {"status": "added", "id": tid}
    if action == "list":
        return {"todos": m.list_todos()}
    if action == "complete":
        return {"completed": m.complete_todo(int(ti["task_id"]))}
    if action == "delete":
        return {"deleted": m.delete_todo(int(ti["task_id"]))}
    if action == "clear_completed":
        return {"cleared": m.clear_completed_todos()}
    return {"error": f"Unknown todo action: {action}"}
