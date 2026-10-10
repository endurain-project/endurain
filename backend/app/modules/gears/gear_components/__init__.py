"""
Gear components sub-module.

Provides CRUD operations, schemas, and models
for gear component tracking (e.g., chains, tires,
pedals, strings).

Exports:
    - CRUD: get_gear_components_user,
      get_gear_components_user_by_gear_id,
      create_gear_component,
      edit_gear_component,
      delete_gear_component
    - Schemas: GearComponentBase,
      GearComponentCreate, GearComponentRead,
      GearComponentUpdate, GearComponentTypesRead
    - Models: GearComponents (ORM model)
"""

from .crud import (
    create_gear_component,
    delete_gear_component,
    edit_gear_component,
    get_gear_components_user,
    get_gear_components_user_by_gear_id,
)
from .schema import (
    GearComponentBase,
    GearComponentCreate,
    GearComponentRead,
    GearComponentTypesRead,
    GearComponentUpdate,
)

__all__ = [
    "GearComponentBase",
    "GearComponentCreate",
    "GearComponentRead",
    "GearComponentTypesRead",
    "GearComponentUpdate",
    "create_gear_component",
    "delete_gear_component",
    "edit_gear_component",
    "get_gear_components_user",
    "get_gear_components_user_by_gear_id",
]
