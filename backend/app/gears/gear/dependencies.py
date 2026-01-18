import core.dependencies as core_dependencies

def validate_gear_id(gear_id: int):
    """
    Validates that the provided gear_id is greater than zero.

    Args:
        gear_id (int): The ID of the gear to validate.

    Raises:
        ValueError: If the gear_id is not greater than zero.
    """
    # Check if id higher than 0
    core_dependencies.validate_id(id=gear_id, min=0, message="Invalid gear ID")

def validate_gear_type(gear_type: int):
    """
    Validates that the provided gear_type is within the allowed range.

    Args:
        gear_type (int): The type of gear to validate.

    Raises:
        ValueError: If gear_type is not between 1 and 9 (inclusive).

    Returns:
        None
    """
    # Check if gear type is within 1 and 9 (9 = watch/computer)
    core_dependencies.validate_type(type=gear_type, min=1, max=9, message="Invalid gear type")