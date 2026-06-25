"""LLM client (OpenRouter, OpenAI-compatible) + the full tool catalogue.

TOOLS is the authoritative list of tools ARIA exposes to the model, written
in the compact Anthropic-style schema. `to_openai_tools()` converts them to
the OpenAI function-calling format that OpenRouter expects. Not every tool
has a backend handler yet — handlers are added phase by phase in
core/tools.py; tools without one return a friendly "not implemented" result.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from config import Settings

TOOLS: list[dict] = [
    # ---------- System ----------
    {
        "name": "run_shell_command",
        "description": "Execute a PowerShell or CMD command on the user's Windows machine. Use for OS tasks, file operations via CLI, running scripts, checking system info, network commands, etc. ALWAYS explain what the command does before running it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The full shell command to run"},
                "shell": {"type": "string", "enum": ["powershell", "cmd"], "default": "powershell"},
                "working_directory": {"type": "string", "description": "Optional working directory path"},
                "timeout_seconds": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file. Supports .txt, .py, .js, .ts, .json, .csv, .md, .docx, .xlsx, .pdf, .html, .xml, .yaml, and most code files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute or relative file path"},
                "encoding": {"type": "string", "default": "utf-8"},
                "max_chars": {"type": "integer", "default": 50000},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file with the given content. Use for creating new files, saving code, writing reports, updating configs, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["write", "append"], "default": "write"},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List the contents of a directory. Returns file names, sizes, and types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory_path": {"type": "string"},
                "recursive": {"type": "boolean", "default": False},
                "include_hidden": {"type": "boolean", "default": False},
                "filter_extension": {"type": "string", "description": "e.g. '.py' to show only Python files"},
            },
            "required": ["directory_path"],
        },
    },
    {
        "name": "move_or_copy_file",
        "description": "Move or copy a file or directory to a new location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_path": {"type": "string"},
                "destination_path": {"type": "string"},
                "operation": {"type": "string", "enum": ["move", "copy"]},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["source_path", "destination_path", "operation"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file or empty directory. ALWAYS requires user confirmation. Use with caution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "send_to_recycle_bin": {"type": "boolean", "default": True},
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for files matching a pattern in a directory, or search for text content inside files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_path": {"type": "string"},
                "pattern": {"type": "string", "description": "Glob pattern like '*.py' or keyword to search inside files"},
                "search_type": {"type": "string", "enum": ["filename", "content"], "default": "filename"},
                "recursive": {"type": "boolean", "default": True},
            },
            "required": ["search_path", "pattern"],
        },
    },
    {
        "name": "open_application",
        "description": "Open an installed application by name or executable path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "e.g. 'notepad', 'chrome', 'vscode', 'excel'"},
                "arguments": {"type": "string", "description": "Optional arguments to pass to the application"},
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "get_system_info",
        "description": "Get system information: CPU usage, RAM, disk space, running processes, network status, battery level, time, environment variables, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "info_type": {
                    "type": "string",
                    "enum": ["cpu", "ram", "disk", "processes", "network", "battery", "datetime", "env_vars", "all"],
                }
            },
            "required": ["info_type"],
        },
    },
    {
        "name": "clipboard_read",
        "description": "Read the current content of the system clipboard.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clipboard_write",
        "description": "Write text content to the system clipboard.",
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Take a screenshot of the current screen and optionally OCR the text from it. Useful to see what's currently visible on screen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "save_path": {"type": "string", "description": "Optional path to save the screenshot"},
                "ocr": {"type": "boolean", "default": False},
            },
        },
    },
    # ---------- Web ----------
    {
        "name": "web_search",
        "description": "Search the web using DuckDuckGo. Returns titles, URLs, and snippets for the top results. Use this before scraping to find the right URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "scrape_webpage",
        "description": "Fetch and extract clean text content from a URL. Use for reading articles, documentation, prices, product info, news, etc. Handles JavaScript-heavy pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "extract_mode": {"type": "string", "enum": ["text", "markdown", "links", "tables", "images"], "default": "text"},
                "wait_for_js": {"type": "boolean", "default": False},
            },
            "required": ["url"],
        },
    },
    {
        "name": "download_file",
        "description": "Download a file from a URL and save it to a local path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "save_path": {"type": "string"},
            },
            "required": ["url", "save_path"],
        },
    },
    # ---------- Memory ----------
    {
        "name": "remember_fact",
        "description": "Store an important fact or user preference in long-term memory. Use for info the user wants ARIA to remember across sessions: names, preferences, frequently used paths, project details, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
                "category": {"type": "string", "enum": ["preference", "person", "project", "location", "task", "fact", "other"]},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "recall_memory",
        "description": "Search long-term memory for relevant facts. Call this when the user references something you might have stored previously.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    # ---------- Tasks ----------
    {
        "name": "set_reminder",
        "description": "Set a reminder or scheduled task. ARIA will notify the user at the specified time via system notification and voice.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "datetime_str": {"type": "string", "description": "ISO format or natural language like '2024-01-15 14:30' or 'tomorrow at 3pm'"},
                "repeat": {"type": "string", "enum": ["none", "daily", "weekly", "monthly"], "default": "none"},
            },
            "required": ["message", "datetime_str"],
        },
    },
    {
        "name": "manage_todo",
        "description": "Add, list, complete, or delete to-do items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "list", "complete", "delete", "clear_completed"]},
                "task": {"type": "string", "description": "Task description (for add)"},
                "task_id": {"type": "integer", "description": "Task ID (for complete/delete)"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "read_email",
        "description": "Read recent emails from the configured email account. Returns subject, sender, date, and body preview.",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "default": "INBOX"},
                "max_emails": {"type": "integer", "default": 10},
                "unread_only": {"type": "boolean", "default": True},
                "search_query": {"type": "string", "description": "Optional: filter by keyword in subject/body"},
            },
        },
    },
    {
        "name": "send_email",
        "description": "Send an email from the configured email account. Always confirms with user before sending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
]


def to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert the Anthropic-style schema to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


OPENAI_TOOLS = to_openai_tools(TOOLS)


class LLMClient:
    """Async wrapper around an OpenAI-compatible chat-completions endpoint
    (OpenRouter by default)."""

    def __init__(self, settings: Settings):
        if not settings.has_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to your .env file."
            )
        self.settings = settings
        headers = {}
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers=headers or None,
        )

    async def create(self, system: str, messages: list[dict]):
        """Return the assistant message from one completion call.

        `messages` is the OpenAI-format running history (without the system
        message, which is prepended here).
        """
        full = [{"role": "system", "content": system}, *messages]
        response = await self.client.chat.completions.create(
            model=self.settings.model,
            max_tokens=self.settings.max_tokens,
            tools=OPENAI_TOOLS,
            messages=full,
        )
        return response.choices[0].message
