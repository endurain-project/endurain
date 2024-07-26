import dependencies_global

def validate_activity_id(activity_id: int):
    # Check if id higher than 0
    dependencies_global.validate_id(id=activity_id, min=0, message="Invalid activity ID")

def validate_week_number(week_number: int):
    # Check if gear type is between 0 and 52
    dependencies_global.validate_type(type=week_number, min=0, max=52, message="Invalid week number")
