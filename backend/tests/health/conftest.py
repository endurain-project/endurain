"""Shared setup for the health tests."""

import model_registry

# The ``Users`` mapper resolves its relationships by name, so a health test that
# compiles a statement needs every model imported even when run on its own.
model_registry.import_all_models()
