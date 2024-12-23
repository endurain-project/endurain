import os

import core.logger as core_logger

# Constant related to version
API_VERSION = "v0.7.0"


def check_required_env_vars():
    required_env_vars = [
        "TZ",
        "DB_TYPE",
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASSWORD",
        "DB_DATABASE",
        "SECRET_KEY",
        "ALGORITHM",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_DAYS",
        "STRAVA_CLIENT_ID",
        "STRAVA_CLIENT_SECRET",
        "STRAVA_AUTH_CODE",
        "JAEGER_ENABLED",
        "JAEGER_PROTOCOL",
        "JAEGER_HOST",
        "JAGGER_PORT",
        "ENDURAIN_HOST",
        "GEOCODES_MAPS_API",
    ]

    for var in required_env_vars:
        if var not in os.environ:
            core_logger.print_to_log_and_console(f"Missing required environment variable: {var}", "error")
            raise EnvironmentError(f"Missing required environment variable: {var}")
