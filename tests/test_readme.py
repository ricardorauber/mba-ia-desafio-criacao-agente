import re

from aurora import config

REFERENCE = re.compile(r"`(aurora/[\w/]+\.py)(?:::([\w.]+))?`")


def _guarantees_section() -> str:
    text = (config.ROOT_DIR / "README.md").read_text(encoding="utf-8")
    start = text.index("## Garantias")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_guarantee_references_exist():
    references = REFERENCE.findall(_guarantees_section())
    assert len(references) >= 10
    for path, symbol in references:
        source_file = config.ROOT_DIR / path
        assert source_file.is_file(), path
        if symbol:
            source = source_file.read_text(encoding="utf-8")
            for name in symbol.split("."):
                pattern = rf"^\s*(?:async\s+def|def|class)\s+{name}\b|^{name}\s*="
                assert re.search(pattern, source, re.MULTILINE), f"{path}::{symbol}"
