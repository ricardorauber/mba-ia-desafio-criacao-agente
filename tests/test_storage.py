import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from aurora import config, storage
from aurora.main import run_restore

SEED_CODES = {"RSV-1377", "RSV-4821", "RSV-2950"}


def test_seed_matches_dados():
    run_restore()
    assert storage.list_reservations("101") == [
        {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
    ]
    assert storage.list_visitors("302") == [{"nome": "Marina Duarte", "data": "2030-03-16"}]
    assert storage.apartment_exists("101")
    assert not storage.apartment_exists("999")
    assert storage.get_area("salao-de-festas")["taxa"] == 150.0


def test_unique_active_reservation_enforced_by_index():
    storage.list_areas()
    conn = sqlite3.connect(config.condo_db_path())
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reservas (codigo, apartamento, area, data)"
            " VALUES ('RSV-RAW001', '101', 'salao-de-festas', '2030-03-16')"
        )
    conn.close()


def test_concurrent_create_only_one_wins():
    storage.list_areas()
    apartments = ["101", "102", "201", "202", "301"] * 4
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(
            pool.map(
                lambda apt: storage.create_reservation(apt, "salao-de-festas", "2030-05-11"),
                apartments,
            )
        )
    winners = [code for code in results if code is not None]
    assert len(winners) == 1
    assert results.count(None) == 19


def test_codes_never_repeat_after_cancel_and_restore():
    issued = set()
    for day in range(1, 6):
        code = storage.create_reservation("101", "quadra", f"2030-06-0{day}")
        issued.add(code)
    assert storage.cancel_reservation("101", "quadra", "2030-06-01")
    storage.save_session("s-1", "101")
    storage.restore()
    for day in range(1, 6):
        issued.add(storage.create_reservation("101", "quadra", f"2030-07-0{day}"))
    assert len(issued) == 10
    assert not issued & SEED_CODES
    assert all(code.startswith("RSV-") and len(code) == 10 for code in issued)
    conn = sqlite3.connect(config.condo_db_path())
    ledger = {row[0] for row in conn.execute("SELECT codigo FROM codigos_reserva")}
    conn.close()
    assert issued | SEED_CODES <= ledger
    assert storage.session_apartment("s-1") == "101"


def test_cancel_only_own_reservation():
    assert storage.cancel_reservation("101", "salao-de-festas", "2030-03-16") is None
    assert storage.list_reservations("302")[0]["codigo"] == "RSV-4821"


def test_rebook_after_cancel():
    assert storage.cancel_reservation("101", "quadra", "2030-03-09") == "RSV-1377"
    assert storage.list_reservations("101") == []
    code = storage.create_reservation("102", "quadra", "2030-03-09")
    assert code is not None
    assert storage.list_reservations("102") == [
        {"codigo": code, "area": "quadra", "data": "2030-03-09"}
    ]
