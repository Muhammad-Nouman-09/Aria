"""Settings screen — toggle the common permission/feature flags.

Changes apply to the running session immediately and are persisted to .env so
they survive restarts. The startup toggle writes the Windows Run key.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGroupBox,
                             QLabel, QVBoxLayout)

from config import Settings, update_env_value
from modules.system.startup import is_startup_enabled, set_startup

# (settings attribute, .env key, label)
TOGGLES = [
    ("require_approval_for_shell", "REQUIRE_APPROVAL_FOR_SHELL",
     "Ask before running shell commands"),
    ("require_approval_for_file_write", "REQUIRE_APPROVAL_FOR_FILE_WRITE",
     "Ask before writing/moving files"),
    ("require_approval_for_delete", "REQUIRE_APPROVAL_FOR_DELETE",
     "Ask before deleting files"),
    ("allow_shell_commands", "ALLOW_SHELL_COMMANDS",
     "Allow shell commands at all"),
    ("web_search_enabled", "WEB_SEARCH_ENABLED", "Enable web search"),
    ("scraping_enabled", "SCRAPING_ENABLED", "Enable web scraping"),
    ("voice_enabled", "VOICE_ENABLED", "Speak replies by default"),
]


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("ARIA — Settings")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        perms = QGroupBox("Permissions & features")
        pv = QVBoxLayout(perms)
        self._checks: dict[str, QCheckBox] = {}
        for attr, _env, label in TOGGLES:
            cb = QCheckBox(label)
            cb.setChecked(bool(getattr(settings, attr)))
            pv.addWidget(cb)
            self._checks[attr] = cb
        layout.addWidget(perms)

        startup = QGroupBox("System")
        sv = QVBoxLayout(startup)
        self.startup_cb = QCheckBox("Launch ARIA when Windows starts")
        self.startup_cb.setChecked(is_startup_enabled())
        sv.addWidget(self.startup_cb)
        layout.addWidget(startup)

        layout.addWidget(QLabel("Changes are saved to .env and applied now."))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        env_map = {attr: env for attr, env, _ in TOGGLES}
        for attr, cb in self._checks.items():
            value = cb.isChecked()
            setattr(self.settings, attr, value)
            update_env_value(env_map[attr], "true" if value else "false")

        want_startup = self.startup_cb.isChecked()
        set_startup(want_startup)
        self.settings.startup_with_windows = want_startup
        update_env_value("STARTUP_WITH_WINDOWS",
                         "true" if want_startup else "false")
        self.accept()
