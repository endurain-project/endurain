import logging


def setup_migration_logger():
    # Create loggger
    migration_logger = logging.getLogger("migration_logger")
    migration_logger.setLevel(logging.DEBUG)

    file_handler = logging.FileHandler("logs/migrations.log")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    migration_logger.addHandler(file_handler)
    return migration_logger


def get_migration_logger():
    return logging.getLogger("migration_logger")


def print_to_log(message: str, type: str = "info"):
    migration_logger = get_migration_logger()
    if type == "info":
        migration_logger.info(message)
    elif type == "error":
        migration_logger.error(message)
    elif type == "warning":
        migration_logger.warning(message)
    elif type == "debug":
        migration_logger.debug(message)


def print_to_log_and_console(message: str, type: str = "info"):
    print_to_log(message, type)
    print(message)
