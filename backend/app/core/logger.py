import logging

import core.config as core_config


def setup_main_logger():
    """
    Sets up the main application logger and attaches a file handler to it, as well as to the Alembic and APScheduler loggers.

    The logger writes log messages to 'logs/app.log' with a specific format and log level.
    - The main logger ('main_logger') uses the LOG_LEVEL from configuration (default: WARNING).
    - The Alembic logger ('alembic') and APScheduler logger ('apscheduler') are set to INFO level.
    - All three loggers share the same file handler and formatter.

    Returns:
        logging.Logger: The configured main logger instance.
    """
    # Map string log levels to Python logging constants
    log_level_map = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
        "trace": logging.DEBUG,  # Map trace to debug (Python logging doesn't have trace)
    }

    # Get log level from config, default to WARNING if invalid
    log_level = log_level_map.get(core_config.LOG_LEVEL.lower(), logging.WARNING)

    main_logger = logging.getLogger("main_logger")
    main_logger.setLevel(log_level)

    file_handler = logging.FileHandler(f"{core_config.LOGS_DIR}/app.log")
    file_handler.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    main_logger.addHandler(file_handler)

    # Attach the same handler to Alembic's logger
    alembic_logger = logging.getLogger("alembic")
    alembic_logger.setLevel(log_level)
    alembic_logger.addHandler(file_handler)

    # Attach the same handler to sheduler's logger
    scheduler_logger = logging.getLogger("apscheduler")
    scheduler_logger.setLevel(log_level)
    scheduler_logger.addHandler(file_handler)

    return main_logger


def get_main_logger():
    """
    Returns the main logger instance for the application.

    This function retrieves a logger named "main_logger" using Python's standard logging module.
    It can be used throughout the application to log messages under a consistent logger name.

    Returns:
        logging.Logger: The logger instance named "main_logger".
    """
    return logging.getLogger("main_logger")


def print_to_log(
    message: str, log_level: str = "info", exc: Exception = None, context=None
):
    """
    Logs a message at the specified log level using the main logger.

    Args:
        message (str): The message to log.
        log_level (str, optional): The log level to use ('info', 'error', 'warning', 'debug'). Defaults to "info".
        exc (Exception, optional): An exception instance to include in the log if log_level is "error". Defaults to None.

    Notes:
        - If log_level is "error" and exc is provided, exception information will be included in the log.
    """
    main_logger = get_main_logger()
    if log_level == "info":
        main_logger.info(message)
    elif log_level == "error":
        main_logger.error(message, exc_info=exc is not None)
    elif log_level == "warning":
        main_logger.warning(message)
    elif log_level == "debug":
        main_logger.debug(message)


def print_to_console(message: str, log_level: str = "info"):
    """
    Prints a message to the console only (without logging to file).

    Args:
        message (str): The message to print.
        log_level (str, optional): The log level to display ('info', 'error', 'warning', 'debug'). Defaults to "info".
    """
    if log_level == "info":
        print(f"INFO:     {message}")
    elif log_level == "error":
        print(f"ERROR:    {message}")
    elif log_level == "warning":
        print(f"WARNING:  {message}")
    elif log_level == "debug":
        print(f"DEBUG:    {message}")


def print_to_log_and_console(
    message: str, log_level: str = "info", exc: Exception = None
):
    """
    Logs a message to both the main logger and the console.

    This function temporarily adds a console handler to the main logger, logs the provided message at the specified log level (optionally including exception information), and then removes the console handler to ensure subsequent logs are not printed to the console.

    Args:
        message (str): The message to log.
        log_level (str, optional): The logging level to use (e.g., "info", "warning", "error"). Defaults to "info".
        exc (Exception, optional): An exception to include in the log entry. Defaults to None.
    """
    main_logger = get_main_logger()

    # Create a temporary console handler
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter("%(levelname)s:     %(message)s")
    console_handler.setFormatter(console_formatter)

    # Add console handler temporarily
    main_logger.addHandler(console_handler)

    print_to_log(message, log_level, exc)

    # Remove console handler so future logs only go to file
    main_logger.removeHandler(console_handler)
