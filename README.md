# Residencial Aurora — assistente virtual com Google ADK

Assistente do aplicativo dos moradores do Residencial Aurora: reserva e cancela áreas comuns, autoriza visitantes e tira dúvidas sobre o regulamento interno, exposto por uma API em `http://localhost:8000`.

O princípio do projeto: **o modelo decide o caminho, o código decide o que é permitido.** As regras críticas (confirmação, apartamento da sessão, exclusividade da reserva, regulamento fora do histórico) estão no código e no banco, não no prompt.

## Arquitetura

```
morador ──HTTP──▶ FastAPI (aurora/api.py)
                    │  Conversation (aurora/conversation.py): lock por sessão, pendências, retomada
                    ▼
                 Runner + App resumível (aurora/agents.py) ── SqliteSessionService (var/sessoes.db)
                    │
              coordenador ──transferência──▶ reservas    ─┐
                    │       ──transferência──▶ visitantes ─┴─▶ tools (aurora/tools.py) ─▶ SQLite (var/aurora.db)
                    │
                    └── (coordenador, reservas e visitantes) ──AgentTool──▶ regulamento
                                                   └─▶ listar_capitulos / ler_capitulo (aurora/regulamento.py)
```

| Agente | Responsabilidade | Como é acionado | Por quê |
|---|---|---|---|
| `coordenador` (principal) | Recebe o morador, conversa e distribui o trabalho. Não tem tools de dados nem o regulamento nas instruções. | Raiz do `App`; atende toda mensagem nova que não esteja com um especialista ativo. | Um único ponto de entrada, com instruções curtas e baratas. |
| `reservas` | Lista áreas, consulta disponibilidade, reserva e cancela reservas do apartamento da sessão. | `sub_agent` do coordenador, acionado por `transfer_to_agent`. | O pedido de confirmação precisa ficar gravado na sessão do morador e ser respondido ao agente que o fez. Um sub-agente grava seus eventos na sessão persistida; o Runner do ADK roteia a resposta da confirmação de volta para ele (ADR 0004). |
| `visitantes` | Lista e autoriza visitantes do apartamento da sessão. | `sub_agent` do coordenador, por `transfer_to_agent`. | Mesmo motivo: a autorização de entrada exige confirmação persistida. |
| `regulamento` | Responde dúvidas consultando um capítulo do `dados/regulamento.md` por vez. | `AgentTool` (chamado como uma ferramenta) do coordenador e também dos dois especialistas, para que uma dúvida feita enquanto um especialista está ativo seja respondida pelo regulamento e não de memória. | O `AgentTool` roda o especialista numa sessão própria e efêmera: o índice e o texto dos capítulos lidos não entram na sessão do morador; só a resposta final entra. Assim o regulamento é consultado, não carregado. |

Depois que um especialista responde, a próxima mensagem começa nele (comportamento padrão do ADK); para outro assunto ele transfere de volta ao `coordenador`.

Modelo: todos os agentes usam `gemini-3.8-flash` (estável e recomendado na lista oficial de modelos), com novas tentativas automáticas para erros transitórios e de cota. Pode ser trocado por `AURORA_MODEL`.

Robustez da API: falha do provedor numa mensagem responde `503`; qualquer outra falha inesperada de um turno responde `200` com um pedido de desculpas, sem `500`. Na rota de confirmações, se o modelo falhar depois que a ação já foi executada, a resposta é `200` com o resultado gravado (por exemplo, o código da reserva).

Persistência: tudo em SQLite, sem serviço externo. `var/sessoes.db` guarda as sessões e eventos do ADK (`SqliteSessionService`); `var/aurora.db` guarda áreas, apartamentos, reservas, visitantes, o livro de códigos de reserva já emitidos e o vínculo sessão → apartamento.

Decisões registradas em [`adrs/`](adrs/) e especificações em [`specs/`](specs/).

## Garantias

### Garantia 1 — cobrança ou acesso só com confirmação

- `aurora/tools.py::reservar_area`: para área com `taxa > 0` e sem confirmação, chama `tool_context.request_confirmation(...)` com `area`, `nome_area`, `data` e `taxa` no `payload` e devolve `aguardando_confirmacao` sem gravar. Só grava quando `tool_context.tool_confirmation.confirmed` é verdadeiro. A quadra (taxa zero) grava direto.
- `aurora/tools.py::autorizar_visitante`: sempre pede confirmação (`payload` com `nome` e `data`) antes de gravar.
- `aurora/conversation.py::pending_confirmations`: a lista `confirmacoes_pendentes` é derivada dos eventos persistidos — chamadas `adk_request_confirmation` emitidas pelo próprio ADK (o id está em `long_running_tool_ids` do evento) e sem resposta do usuário com o mesmo id. Uma chamada desse tipo escrita pelo modelo não conta.
- `aurora/conversation.py::Conversation.answer_confirmation` (rota `aurora/api.py::responder_confirmacao`): sob o lock da sessão, aceita só um `id` que esteja nessa lista (senão `409`, sem executar nada) e envia ao Runner um `FunctionResponse` `adk_request_confirmation` com `{"confirmed": ...}`; o ADK retoma o agente que pediu e reexecuta a tool uma única vez.
- `aurora/agents.py::build_app`: `App` resumível, então a execução para no pedido de confirmação (a `resposta` pode vir vazia).

Por que não depende do modelo: a rota de mensagens só envia texto ao Runner. Um "já estou confirmando aqui" é texto e nunca vira `FunctionResponse`; a única forma de produzir `tool_confirmation` é a rota de confirmações, que valida o id contra a sessão.

### Garantia 2 — cada sessão pertence a um apartamento

- `aurora/conversation.py::Conversation.create_session`: cria a sessão do ADK com `user_id` igual ao apartamento informado em `POST /sessoes` e grava o vínculo em `sessoes` (`aurora/storage.py::save_session`).
- `aurora/tools.py::_apartment`: todas as tools leem o apartamento de `tool_context.user_id`. Nenhuma tool tem parâmetro de apartamento.
- `aurora/tools.py::verificar_disponibilidade` devolve só `disponivel: true/false`; `aurora/tools.py::cancelar_reserva` só cancela reserva do próprio apartamento e, quando não encontra, não diz se a data é de outro apartamento; `aurora/storage.py::cancel_reservation` filtra por apartamento no SQL.

Por que não depende do modelo: o `user_id` da sessão é fixado pelo servidor na criação e nenhum evento, `state_delta` ou saída do modelo o altera. Mesmo que o modelo "acredite" que o morador é do 302, não existe argumento pelo qual ele possa escolher outro apartamento.

### Garantia 3 — nada se perde no reinício

- `aurora/api.py::create_app`: o `Runner` usa `SqliteSessionService` em `var/sessoes.db`; sessões e eventos são lidos do disco a cada turno.
- `aurora/storage.py`: reservas e visitantes em `var/aurora.db`, abertos por operação.
- `aurora/config.py::data_dir`: os dois arquivos ficam em `var/`, fora do Git e intocados pela subida da API.

Por que não depende do modelo: nenhum estado relevante fica em memória. Até uma confirmação pendente sobrevive ao reinício, porque a pendência é derivada dos eventos persistidos e o ADK retoma o agente a partir deles.

### Garantia 4 — o regulamento é consultado, não carregado

- `aurora/agents.py::regulation_tool`: o especialista `regulamento` é um `AgentTool` (do coordenador e dos especialistas, montado em `aurora/agents.py::build_root_agent`); os eventos internos dele (índice e capítulo lido) ficam numa sessão efêmera e não são gravados na sessão do morador.
- `aurora/regulamento.py::ler_capitulo`: devolve um único capítulo; `aurora/regulamento.py::listar_capitulos` devolve só números e títulos.
- `aurora/agents.py::COORDINATOR_INSTRUCTION`: as instruções do agente principal não contêm o regulamento (há teste que verifica que nenhum trecho de 40 caracteres do regulamento aparece em instruções ou descrições).

Por que não depende do modelo: o texto do regulamento só existe dentro da tool do especialista, e a separação de sessões é do runtime do ADK. Na sessão do morador entra apenas a resposta curta do especialista.

### Garantia 5 — dois moradores, uma reserva

- `aurora/storage.py::SCHEMA`: índice único parcial `reservas_area_data_ativa` em `reservas (area, data) WHERE cancelada_em IS NULL`.
- `aurora/storage.py::create_reservation`: grava em uma transação `BEGIN IMMEDIATE`; se o índice rejeitar o `INSERT`, faz rollback e devolve `None`, e a tool responde `indisponivel` normalmente (HTTP `200`).
- `aurora/storage.py::_new_code`: códigos `RSV-XXXXXX` gerados com `secrets` e registrados no livro `codigos_reserva`, que a restauração não apaga — um código nunca se repete, nem de reserva cancelada.

Por que não depende do modelo: a exclusividade é verificada pelo SQLite no instante da gravação, não numa consulta anterior. Duas aprovações simultâneas disputam o mesmo índice e só uma vence.

## Como rodar

Pré-requisitos: Python 3.12+ e [uv](https://docs.astral.sh/uv/). Não há serviço externo: o armazenamento é SQLite em `var/`.

1. Configure o ambiente:

   ```bash
   cp .env.example .env
   ```

   | Variável | Uso |
   |---|---|
   | `GOOGLE_API_KEY` | Chave do Google AI Studio (obrigatória). |
   | `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE`: usa a API do Google AI Studio. |
   | `AURORA_MODEL` | Opcional. Modelo Gemini de todos os agentes; vazio usa o padrão `gemini-3.8-flash`. |

2. Instale as dependências:

   ```bash
   uv sync
   ```

3. Restaure os dados iniciais (reservas e visitantes voltam ao estado de `dados/`; sessões e códigos já emitidos são mantidos):

   ```bash
   uv run aurora-restaurar
   ```

4. Suba a API em `http://localhost:8000` (Ctrl+C para parar; subir de novo mantém sessões e dados):

   ```bash
   uv run aurora-api
   ```

Para ver transferências, tools e confirmações durante o desenvolvimento: `uv run adk web .` na raiz e escolha `aurora`.

Testes (com um modelo roteirizado no lugar do Gemini, sem chave): `uv run pytest`. Eles exercitam o `Runner`, a API e o SQLite de verdade, inclusive confirmação depois de reiniciar e duas aprovações simultâneas. O fluxo completo ainda não foi executado contra o Gemini real (ADR 0008).

Fluxo do avaliador contra a API rodando (passos 1–12, depois reinicie a API e rode os passos 13–14):

```bash
uv run python scripts/fluxo_avaliador.py --ate-12
uv run python scripts/fluxo_avaliador.py --depois-do-reinicio
```
