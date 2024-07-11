from dependencies import dependencies_global


def validate_user_id(user_id: int):
    # Check if id higher than 0
    dependencies_global.validate_id(id=user_id, min=0, message="Invalid user ID")


def validate_target_user_id(target_user_id: int):
    # Check if id higher than 0
    dependencies_global.validate_id(
        id=target_user_id, min=0, message="Invalid target user ID"
    )
