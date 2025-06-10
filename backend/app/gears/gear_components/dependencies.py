import core.dependencies as core_dependencies

def validate_gear_component_id(gear_component_id: int):
    # Check if id higher than 0
    core_dependencies.validate_id(id=gear_component_id, min=0, message="Invalid gear component ID")