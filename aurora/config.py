"""Filesystem locations used by the application."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT_DIR / "dados"


def data_dir() -> Path:
    """Directory holding the runtime databases (created on demand)."""
    path = Path(os.environ.get("AURORA_DATA_DIR") or ROOT_DIR / "var")
    path.mkdir(parents=True, exist_ok=True)
    return path


def condo_db_path() -> Path:
    return data_dir() / "aurora.db"


def sessions_db_path() -> Path:
    return data_dir() / "sessoes.db"
