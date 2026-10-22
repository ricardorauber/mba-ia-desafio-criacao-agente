"""Console entry points."""

from aurora import storage


def run_api() -> None:
    print("aurora-api: not implemented yet")


def run_restore() -> None:
    storage.restore()
    print("Dados restaurados: reservas e visitantes voltaram ao estado de dados/.")
