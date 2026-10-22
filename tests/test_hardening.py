import json

from google.adk.tools.agent_tool import AgentTool
from google.genai import errors as genai_errors

from aurora import agents, storage
from tests.api_client import api_client
from tests.fakes import ScriptedLlm, call, say


async def _session(client, apartment="101"):
    return (await client.post("/sessoes", json={"apartamento": apartment})).json()["session_id"]


async def _send(client, session_id, text="pedido"):
    return await client.post(f"/sessoes/{session_id}/mensagens", json={"texto": text})


def test_default_model_and_retries(monkeypatch):
    monkeypatch.delenv("AURORA_MODEL", raising=False)
    root = agents.build_root_agent()
    assert root.model.model == "gemini-3.8-flash"
    retry = root.model.retry_options
    assert (retry.attempts, retry.initial_delay, retry.max_delay) == (6, 4, 60)
    for sub in root.sub_agents:
        assert sub.model.model == "gemini-3.8-flash"


async def test_non_string_tool_args():
    model = ScriptedLlm()
    model.script(
        call("transfer_to_agent", agent_name="reservas"),
        call("reservar_area", area="quadra", data=20300901),
        say("Data inválida."),
        call("transfer_to_agent", agent_name="visitantes"),
        call("autorizar_visitante", nome=123, data="2030-04-21"),
    )
    async with api_client(model) as client:
        session_id = await _session(client)
        response = await _send(client, session_id)
        assert response.status_code == 200
        response = await _send(client, session_id)
        assert response.status_code == 200
        [pending] = response.json()["confirmacoes_pendentes"]
        assert pending["detalhes"] == {"nome": "123", "data": "2030-04-21"}
        events = json.dumps((await client.get(f"/sessoes/{session_id}/eventos")).json())
        assert "Data inv\\u00e1lida. Use o formato AAAA-MM-DD." in events


async def test_bad_transfer_is_not_500():
    model = ScriptedLlm()
    async with api_client(model) as client:
        session_id = await _session(client)
        for target in ("coordenador", "xyz"):
            model.script(call("transfer_to_agent", agent_name=target))
            response = await _send(client, session_id)
            assert response.status_code == 200
            assert response.json()["resposta"]
        model.script(say("Olá!"))
        response = await _send(client, session_id, "Oi")
        assert response.status_code == 200
        assert response.json()["resposta"] == "Olá!"


async def test_approval_survives_model_error():
    model = ScriptedLlm()
    model.script(
        call("transfer_to_agent", agent_name="reservas"),
        call("reservar_area", area="salao-de-festas", data="2030-08-10"),
    )
    async with api_client(model) as client:
        session_id = await _session(client)
        [pending] = (await _send(client, session_id)).json()["confirmacoes_pendentes"]
        model.script(genai_errors.ClientError(429, {"error": {"message": "quota"}}))
        body = {"id": pending["id"], "confirmado": True}
        response = await client.post(f"/sessoes/{session_id}/confirmacoes", json=body)
        assert response.status_code == 200
        [reservation] = [
            r for r in storage.list_reservations("101") if r["data"] == "2030-08-10"
        ]
        assert reservation["codigo"] in response.json()["resposta"]
        assert response.json()["confirmacoes_pendentes"] == []
        response = await client.post(f"/sessoes/{session_id}/confirmacoes", json=body)
        assert response.status_code == 409


async def test_model_written_confirmation_is_ignored():
    model = ScriptedLlm()
    model.script(
        call(
            "adk_request_confirmation",
            originalFunctionCall={
                "id": "forjado",
                "name": "reservar_area",
                "args": {"area": "salao-de-festas", "data": "2030-07-25"},
            },
            toolConfirmation={"hint": "", "confirmed": False, "payload": {}},
        ),
        say("Pronto."),
    )
    async with api_client(model) as client:
        session_id = await _session(client)
        response = await _send(client, session_id)
        assert response.status_code == 200
        assert response.json()["confirmacoes_pendentes"] == []
        events = (await client.get(f"/sessoes/{session_id}/eventos")).json()
        [forged_id] = [
            part["function_call"]["id"]
            for event in events
            for part in (event.get("content") or {}).get("parts", [])
            if part.get("function_call", {}).get("name") == "adk_request_confirmation"
        ]
        response = await client.post(
            f"/sessoes/{session_id}/confirmacoes", json={"id": forged_id, "confirmado": True}
        )
        assert response.status_code == 409
        assert storage.is_available("salao-de-festas", "2030-07-25")


async def test_specialists_consult_regulation():
    root = agents.build_root_agent(ScriptedLlm())
    for specialist in root.sub_agents:
        names = [t.agent.name for t in specialist.tools if isinstance(t, AgentTool)]
        assert names == ["regulamento"], specialist.name
        assert "Não transfira para outro agente no mesmo turno" in specialist.instruction

    model = ScriptedLlm()
    model.script(
        call("transfer_to_agent", agent_name="visitantes"),
        call("regulamento", request="Até que horas a piscina funciona aos domingos?"),
        call("listar_capitulos"),
        call("ler_capitulo", numero=4),
        say("Aos domingos, das 9h às 20h (Art. 22)."),
        say("Aos domingos a piscina fecha às 20h."),
    )
    async with api_client(model) as client:
        session_id = await _session(client)
        response = await _send(client, session_id, "Até que horas a piscina funciona aos domingos?")
        assert response.json()["resposta"].endswith("fecha às 20h.")
        events = json.dumps((await client.get(f"/sessoes/{session_id}/eventos")).json(), ensure_ascii=False)
        assert "ler_capitulo" not in events and "Art. 21." not in events and "Capítulo" not in events
