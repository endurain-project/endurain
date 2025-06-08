import core.dependencies as core_dependencies

def validate_activity_stream_type(stream_type: int):
    # Check if gear type is between 1 and 7
    core_dependencies.validate_type(type=stream_type, min=1, max=7, message="Invalid activity stream type")