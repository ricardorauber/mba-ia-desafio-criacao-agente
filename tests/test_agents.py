import json

from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.tools.agent_tool import AgentTool

from aurora import agents, config, storage
from tests.fakes import (
    ScriptedLlm,
    call,
    confirmation_answer,
    function_responses,
    open_confirmations,
    say,
    user_text,
)


def _all_agents(root):
    found = [root]
    for sub in root.sub_agents:
        found.extend(_all_agents(sub))
    for tool in root.tools:
        if isinstance(tool, AgentTool):
            found.extend(_all_agents(tool.agent))
    return found


def test_tree_shape():
    root = agents.build_root_agent(ScriptedLlm())
    assert root.name == "coordenador"
    assert [sub.name for sub in root.sub_agents] == ["reservas", "visitantes"]
    [tool] = root.tools
    assert isinstance(tool, AgentTool) and tool.agent.name == "regulamento"
    assert agents.build_app(ScriptedLlm()).resumability_config.is_resumable


def test_regulation_not_in_instructions():
    text = " ".join((config.DADOS_DIR / "regulamento.md").read_text(encoding="utf-8").split())
    windows = {text[i : i + 40] for i in range(0, len(text) - 40)}
    for agent in _all_agents(agents.build_root_agent(ScriptedLlm())):
        prompt = " ".join(f"{agent.instruction} {agent.description}".split())
        assert not any(window in prompt for window in windows), agent.name


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("AURORA_MODEL", "gemini-teste")
    assert agents.build_root_agent().model.model == "gemini-teste"
    monkeypatch.delenv("AURORA_MODEL")
    assert agents.build_root_agent().model.model == agents.DEFAULT_MODEL


async def _turn(runner, session_id, content, user_id="101"):
    async for _ in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        pass
    return await runner.session_service.get_session(
        app_name=agents.APP_NAME, user_id=user_id, session_id=session_id
    )


def _runner(model):
    service = SqliteSessionService(db_path=str(config.sessions_db_path()))
    return Runner(app=agents.build_app(model), session_service=service)


async def _new_session(runner, apartment="101"):
    session = await runner.session_service.create_session(
        app_name=agents.APP_NAME, user_id=apartment, state={"apartamento": apartment}
    )
    return session.id


async def test_regulation_events_stay_out_of_session():
    model = ScriptedLlm()
    model.script(
        call("regulamento", request="Até que horas a piscina funciona aos domingos?"),
        call("listar_capitulos"),
        call("ler_capitulo", numero=4),
        say("Aos domingos a piscina funciona das 9h às 20h (Art. 22)."),
        say("A piscina fecha às 20h aos domingos."),
    )
    runner = _runner(model)
    session_id = await _new_session(runner)
    session = await _turn(runner, session_id, user_text("Até que horas a piscina funciona aos domingos?"))
    names = [
        part.function_call.name if part.function_call else part.function_response.name
        for event in session.events
        for part in (event.content.parts if event.content else [])
        if part.function_call or part.function_response
    ]
    assert names == ["regulamento", "regulamento"]
    dumped = json.dumps([event.model_dump(mode="json") for event in session.events], ensure_ascii=False)
    assert "Art. 21." not in dumped and "exame dermatológico" not in dumped
    assert "Capítulo" not in dumped
    assert function_responses(session, "regulamento")[0]["result"].startswith("Aos domingos")


async def test_confirmation_resumes_after_restart():
    model = ScriptedLlm()
    model.script(
        call("transfer_to_agent", agent_name="reservas"),
        call("reservar_area", area="salao-de-festas", data="2030-04-20"),
    )
    runner = _runner(model)
    session_id = await _new_session(runner)
    session = await _turn(runner, session_id, user_text("Reserve o salão para 2030-04-20"))
    [confirmation_id] = open_confirmations(session)
    assert storage.is_available("salao-de-festas", "2030-04-20")

    restarted = _runner(model)
    model.script(say("Reserva feita."))
    session = await _turn(restarted, session_id, confirmation_answer(confirmation_id, True))
    done = [r for r in function_responses(session, "reservar_area") if r["status"] == "reservada"]
    assert len(done) == 1
    salons = [r for r in storage.list_reservations("101") if r["area"] == "salao-de-festas"]
    assert len(salons) == 1 and salons[0]["codigo"] == done[0]["codigo"]
    assert open_confirmations(session) == {}
