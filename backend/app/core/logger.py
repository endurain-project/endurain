import logging


def setup_main_logger():
    main_logger = logging.getLogger("main_logger")
    main_logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    main_logger.addHandler(file_handler)

    # Attach the same handler to Alembic's logger
    alembic_logger = logging.getLogger("alembic")
    alembic_logger.setLevel(logging.INFO)
    alembic_logger.addHandler(file_handler)

    # Attach the same handler to sheduler's logger
    scheduler_logger = logging.getLogger("apscheduler")
    scheduler_logger.setLevel(logging.INFO)
    scheduler_logger.addHandler(file_handler)

    return main_logger


def get_main_logger():
    return logging.getLogger("main_logger")


def print_to_log(message: str, type: str = "info", exc: Exception = None):
    main_logger = get_main_logger()
    if type == "info":
        main_logger.info(message)
    elif type == "error":
        main_logger.error(message, exc_info=exc is not None)
    elif type == "warning":
        main_logger.warning(message)
    elif type == "debug":
        main_logger.debug(message)


def print_to_log_and_console(message: str, type: str = "info"):
    print_to_log(message, type)
    print(message)
