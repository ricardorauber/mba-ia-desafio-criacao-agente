from aurora import storage
from tests.api_client import api_client
from tests.fakes import ScriptedLlm


async def test_restored_data():
    storage.restore()
    async with api_client(ScriptedLlm()) as client:
        response = await client.get("/apartamentos/101/reservas")
        assert response.status_code == 200
        assert response.json() == [{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}]
        response = await client.get("/apartamentos/302/visitantes")
        assert response.status_code == 200
        assert response.json() == [{"nome": "Marina Duarte", "data": "2030-03-16"}]


async def test_unknown_apartment_is_404():
    async with api_client(ScriptedLlm()) as client:
        assert (await client.get("/apartamentos/999/reservas")).status_code == 404
        assert (await client.get("/apartamentos/999/visitantes")).status_code == 404


async def test_cancelled_reservations_are_hidden():
    storage.cancel_reservation("101", "quadra", "2030-03-09")
    async with api_client(ScriptedLlm()) as client:
        assert (await client.get("/apartamentos/101/reservas")).json() == []
