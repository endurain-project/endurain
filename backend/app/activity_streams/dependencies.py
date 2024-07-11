from dependencies import dependencies_global

def validate_activity_stream_type(stream_type: int):
    # Check if gear type is between 1 and 3
    dependencies_global.validate_type(type=stream_type, min=1, max=7, message="Invalid activity stream type")