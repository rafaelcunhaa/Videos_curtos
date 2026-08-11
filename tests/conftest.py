import os
import tempfile

import pytest

import banco


@pytest.fixture
def banco_teste(monkeypatch):
    """
    Cria um banco de dados temporário para os testes.
    """

    fd, caminho = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Troca o banco real pelo temporário
    monkeypatch.setattr(banco, "BANCO_ARQUIVO", caminho)

    banco.inicializar()

    yield caminho

    if os.path.exists(caminho):
        os.remove(caminho)