from dependencies import dependencies_global

def validate_gear_id(gear_id: int):
    # Check if id higher than 0
    dependencies_global.validate_id(id=gear_id, min=0, message="Invalid gear ID")

def validate_gear_type(gear_type: int):
    # Check if gear type is between 1 and 3
    dependencies_global.validate_type(type=gear_type, min=1, max=3, message="Invalid gear type")