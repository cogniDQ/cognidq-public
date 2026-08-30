"""
Logging configuration
"""

import logging
import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings


def setup_logging():
    """Setup application logging"""

    # FIRST: Completely silence SQLAlchemy and other verbose loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # Disable SQLAlchemy logging completely
    logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy").propagate = False

    # Configure Spark loggers - set to WARNING to show errors but reduce noise
    logging.getLogger("py4j").setLevel(logging.WARNING)
    logging.getLogger("py4j.java_gateway").setLevel(logging.ERROR)
    logging.getLogger("pyspark").setLevel(logging.WARNING)
    logging.getLogger("pyspark.sql").setLevel(logging.INFO)  # Keep SQL execution visible
    logging.getLogger("pyspark.streaming").setLevel(logging.WARNING)

    # Create logs directory if it doesn't exist
    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Remove default logger
    logger.remove()

    # Add console logger with cleaner format
    logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL,
        filter=lambda record: (
            not (
                record["name"].startswith("sqlalchemy")
                or record["name"].startswith("uvicorn.access")
                or record["name"].startswith("py4j.java_gateway")
                or "sqlalchemy" in record["name"].lower()
            )
        ),
    )

    # Add file logger
    logger.add(
        settings.LOG_FILE,
        rotation="500 MB",
        retention="10 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.LOG_LEVEL,
    )

    # Intercept standard logging
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            # Skip SQLAlchemy and other verbose third-party logs
            if record.name.startswith(("sqlalchemy", "uvicorn.access", "py4j.java_gateway")):
                return

            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            frame, depth = logging.currentframe(), 2
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Ensure application loggers are at desired level
    logging.getLogger("app").setLevel(logging.INFO)

    logger.info(f"✅ Logging configured - Level: {settings.LOG_LEVEL}")
