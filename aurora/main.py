"""Console entry points."""

import uvicorn
from dotenv import load_dotenv

from aurora import config, storage

HOST = "127.0.0.1"
PORT = 8000


def run_api() -> None:
    load_dotenv(config.ROOT_DIR / ".env")
    uvicorn.run("aurora.api:create_app", factory=True, host=HOST, port=PORT, workers=1)


def run_restore() -> None:
    storage.restore()
    print("Dados restaurados: reservas e visitantes voltaram ao estado de dados/.")
