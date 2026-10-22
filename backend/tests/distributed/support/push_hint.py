"""Act as a process that holds no sockets, such as the job worker: push a hint to a user.

Run from the ``app`` directory with that process's environment. It builds the platform and
publishes through the websocket surface without subscribing or starting the channel, which
is all a worker does.
"""

# ruff: noqa: E402 - a process entry point: it extends sys.path before importing.

import sys

sys.path.insert(0, ".")

import jasil.container as container
import jasil.lifecycle as lifecycle
import jasil.runtime as runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.platform_settings as core_platform_settings
import model_registry

model_registry.import_all_models()
substrate_settings = core_platform_settings.build_jasil_settings(core_config.settings)
jasil_settings.configure(substrate_settings)
platform = container.build_platform(substrate_settings)
runtime.set_active_platform(platform)

import modules.websocket.integration_service as websocket_integration

websocket_integration.push_to_user(int(sys.argv[1]), {"message": sys.argv[2], "notification_id": 1})

lifecycle.shutdown()
