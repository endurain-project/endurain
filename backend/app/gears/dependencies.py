import core.dependencies as core_dependencies

def validate_gear_id(gear_id: int):
    # Check if id higher than 0
    core_dependencies.validate_id(id=gear_id, min=0, message="Invalid gear ID")

def validate_gear_type(gear_type: int):
    # Check if gear type is between 1 and 3
    core_dependencies.validate_type(type=gear_type, min=1, max=4, message="Invalid gear type")