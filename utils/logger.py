# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def resolve_log_path(log_file: str = "logs/run_{date}.log") -> Path:
    """Build daily log path. Supports {date}; bare run.log becomes run_YYYY-MM-DD.log."""
    today = datetime.now().strftime("%Y-%m-%d")
    if "{date}" in log_file:
        resolved = log_file.replace("{date}", today)
    else:
        path = Path(log_file)
        resolved = str(path.with_name(f"{path.stem}_{today}{path.suffix}"))
    return ROOT / resolved


def setup_logger(log_file: str = "logs/run_{date}.log") -> logging.Logger:
    log_path = resolve_log_path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("sanfeng")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger


def create_output_dir(base_dir: str = "output") -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = ROOT / base_dir / stamp
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))
