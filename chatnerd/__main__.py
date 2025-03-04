import logging
from chatnerd.cli.logging_setup import setup as setup_logging
from chatnerd.config import Config
from chatnerd.cli.cli import app


def init():
    config = Config.instance()

    # Initialise config (Create projects directory, etc)
    config.bootstrap()

    # Setup logging
    _log_terminal_level = logging.DEBUG
    if config.VERBOSE == 0:
        _log_terminal_level = logging.WARNING
    elif config.VERBOSE == 1:
        _log_terminal_level = logging.INFO
    setup_logging(
        log_terminal_level=_log_terminal_level,
        log_file_level=config.LOG_FILE_LEVEL,
        log_file_path=config.LOG_FILE_PATH,
    )


def main():
    init()
    app()


if __name__ == "__main__":
    main()
