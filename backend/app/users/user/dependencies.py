import core.dependencies as core_dependencies


def validate_user_id(user_id: int):
    # Check if id higher than 0
    core_dependencies.validate_id(id=user_id, min=0, message="Invalid user ID")


def validate_target_user_id(target_user_id: int):
    # Check if id higher than 0
    core_dependencies.validate_id(
        id=target_user_id, min=0, message="Invalid target user ID"
    )
