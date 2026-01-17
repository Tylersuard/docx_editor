from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_dir: str | Path | None = None) -> logging.Logger:
    logger = logging.getLogger("genome_traits")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(Path(log_dir) / "run.log")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger
