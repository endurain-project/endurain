import logging


def setup_garminconnect_logger():
    # Create loggger
    garminconnect_logger = logging.getLogger("garminconnect_logger")
    garminconnect_logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler("logs/garminconnect.log")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    garminconnect_logger.addHandler(file_handler)
    return garminconnect_logger


def get_garminconnect_logger():
    return logging.getLogger("garminconnect_logger")


def print_to_log(message: str, type: str = "info"):
    garminconnect_logger = get_garminconnect_logger()
    if type == "info":
        garminconnect_logger.info(message)
    elif type == "error":
        garminconnect_logger.error(message)
    elif type == "warning":
        garminconnect_logger.warning(message)
    elif type == "debug":
        garminconnect_logger.debug(message)


def print_to_log_and_console(message: str, type: str = "info"):
    print_to_log(message, type)
    print(message)
