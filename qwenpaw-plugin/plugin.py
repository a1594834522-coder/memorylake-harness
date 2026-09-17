# -*- coding: utf-8 -*-
"""MemoryLake memory plugin entry point."""

from memorylake_backend import MemoryLakeConfig, MemoryLakeMemoryManager, POLICY_NAMES
from memorylake_backend.routes import build_router
from memorylake_backend.status import handle_status
from qwenpaw.constant import WORKING_DIR
from qwenpaw.plugins.api import PluginApi


class MemoryLakePlugin:
    def register(self, api: PluginApi) -> None:
        api.register_memory_backend(
            backend_id="memorylake",
            factory=MemoryLakeMemoryManager,
            label="MemoryLake",
            config_schema=MemoryLakeConfig,
            metadata={
                "description": (
                    "MemoryLake: long-term memory shared across projects, "
                    "machines, and clients (Claude Code, Codex, dsh, opencode)"
                ),
                "network_access": True,
                "secret_fields": ["api_key"],
                "tools": {
                    "memory_search": {
                        "policy_name": POLICY_NAMES["memory_search"],
                        "tool_type": "network",
                        "target_param": "query",
                    },
                    "memory_remember": {
                        "policy_name": POLICY_NAMES["memory_remember"],
                        "tool_type": "network",
                    },
                    "memory_forget": {
                        "policy_name": POLICY_NAMES["memory_forget"],
                        "tool_type": "network",
                    },
                },
            },
        )
        api.register_slash_command(
            name="memorylake-status",
            handler=handle_status,
            help_text="Show MemoryLake configuration, CLI, login, and connectivity for this Agent",
        )
        # Backs the Console form's workspace / actor pickers.
        api.register_http_router(build_router(WORKING_DIR), prefix="/memorylake", tags=["memorylake"])


plugin = MemoryLakePlugin()
