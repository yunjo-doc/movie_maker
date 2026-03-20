"""로깅 설정"""

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_dir: str = "logs", level: str = "INFO"):
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    detailed_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    simple_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))

    # 콘솔
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(simple_fmt)
    root.addHandler(console)

    # 파일 (전체)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "pipeline.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_fmt)
    root.addHandler(file_handler)

    # 에러 전용
    error_handler = logging.FileHandler(
        log_path / "errors.log", encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_fmt)
    root.addHandler(error_handler)

    # 외부 라이브러리 로그 억제
    for name in ["httpx", "httpcore", "urllib3", "googleapiclient"]:
        logging.getLogger(name).setLevel(logging.WARNING)
