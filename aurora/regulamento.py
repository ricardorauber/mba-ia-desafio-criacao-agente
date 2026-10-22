"""Chapter-level access to ``dados/regulamento.md``.

Only the regulation specialist uses these tools, and it runs as an AgentTool,
so the chapter texts never reach the resident's session.
"""

from __future__ import annotations

import re
from functools import lru_cache

from aurora import config

_CHAPTER_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)


@lru_cache(maxsize=1)
def chapters() -> tuple[dict, ...]:
    text = (config.DADOS_DIR / "regulamento.md").read_text(encoding="utf-8")
    headings = list(_CHAPTER_HEADING.finditer(text))
    result = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        result.append(
            {
                "numero": index + 1,
                "titulo": heading.group(1).strip(),
                "texto": text[heading.start() : end].strip(),
            }
        )
    return tuple(result)


def listar_capitulos() -> dict:
    """Lista o número e o título de cada capítulo do regulamento interno."""
    return {
        "capitulos": [
            {"numero": item["numero"], "titulo": item["titulo"]} for item in chapters()
        ]
    }


def ler_capitulo(numero: int) -> dict:
    """Devolve o texto completo de um único capítulo do regulamento.

    Args:
        numero: número do capítulo, como em listar_capitulos.
    """
    for item in chapters():
        if item["numero"] == numero:
            return dict(item)
    return {
        "status": "erro",
        "mensagem": f"Capítulo inexistente. Use um número de 1 a {len(chapters())}.",
    }
