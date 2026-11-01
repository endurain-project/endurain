"""Act as an API replica: issue a websocket ticket for a user and print it.

Run from the ``app`` directory with the replica's environment. The ticket is written to
the shared state (Redis), so any replica can accept it when the socket connects.
"""

# ruff: noqa: T201 - a process entry point: it extends sys.path before importing, and prints for its parent.

import sys

sys.path.insert(0, ".")

import jasil.container as container
import jasil.lifecycle as lifecycle
import jasil.runtime as runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.platform_settings as core_platform_settings
import model_registry
import module_registry
import modules.websocket.ticket_store as websocket_ticket_store

user_id = int(sys.argv[1])
model_registry.import_all_models()
substrate_settings = core_platform_settings.build_jasil_settings(
    core_config.settings, plain_areas=module_registry.storage_plain_areas()
)
jasil_settings.configure(substrate_settings)
platform = container.build_platform(substrate_settings)
runtime.set_active_platform(platform)

print(f"TICKET {websocket_ticket_store.WsTicketStore(platform.state).create_ticket(user_id)}")

lifecycle.shutdown()
