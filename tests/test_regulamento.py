from aurora import regulamento


def test_chapter_index_and_reader():
    index = regulamento.listar_capitulos()["capitulos"]
    assert len(index) == 14
    assert index[3] == {"numero": 4, "titulo": "Capítulo IV: Piscina"}
    pool = regulamento.ler_capitulo(4)
    assert "das 9h às 20h" in pool["texto"]
    assert pool["texto"].startswith("## Capítulo IV: Piscina")
    assert "Capítulo V" not in pool["texto"]
    assert "Art. 29." not in pool["texto"] and "Art. 20." not in pool["texto"]
    assert regulamento.ler_capitulo(99)["status"] == "erro"
