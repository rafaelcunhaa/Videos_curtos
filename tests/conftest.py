"""
Configuração global de testes - fixtures compartilhadas.
Executa antes de cada teste para preparar ambiente isolado.
"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Generator

import pytest

# Adicionar path do projeto para imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ══════════════════════════════════════════════════════════
# FIXTURES DE BANCO DE DADOS
# ══════════════════════════════════════════════════════════

@pytest.fixture
def banco_teste(monkeypatch):
    """
    Cria um banco de dados temporário para os testes.
    Cada teste recebe um banco vazio e independente.
    """
    fd, caminho = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Troca o banco real pelo temporário
    import banco
    monkeypatch.setattr(banco, "BANCO_ARQUIVO", caminho)

    banco.inicializar()

    yield caminho

    if os.path.exists(caminho):
        os.remove(caminho)


@pytest.fixture
def banco_populado(banco_teste):
    """
    Banco com dados de teste pré-carregados.
    Útil para testes de queries e operações complexas.
    """
    import banco

    # Inserir vídeo de teste
    video_id = banco.registrar_video(
        url="https://youtube.com/watch?v=test123",
        titulo="Vídeo de Teste",
        duracao_s=180.0,
        caminho_arquivo=Path("/tmp/test.mp4")
    )

    # Inserir cortes de teste
    corte1_id = banco.registrar_corte(
        video_id=video_id,
        numero=1,
        corte_info={
            "tipo": "denso",
            "categoria": "podcast",
            "titulo": "Primeiro Corte",
            "gancho": "Gancho de teste",
            "inicio": 0.0,
            "fim": 55.0
        },
        caminho_video=Path("/tmp/corte1.mp4"),
        caminho_txt=Path("/tmp/corte1.txt"),
        desc_info={
            "titulo_yt": "Título YT",
            "descricao": "Descrição teste",
            "hashtags": ["#teste", "#demo"]
        }
    )

    corte2_id = banco.registrar_corte(
        video_id=video_id,
        numero=2,
        corte_info={
            "tipo": "impacto",
            "categoria": "podcast",
            "titulo": "Segundo Corte",
            "gancho": "Outro gancho",
            "inicio": 60.0,
            "fim": 95.0
        },
        caminho_video=Path("/tmp/corte2.mp4"),
        caminho_txt=Path("/tmp/corte2.txt"),
        desc_info=None
    )

    return {
        "video_id": video_id,
        "corte1_id": corte1_id,
        "corte2_id": corte2_id,
        "banco_path": banco_teste
    }


# ══════════════════════════════════════════════════════════
# FIXTURES DE ARQUIVOS TEMPORÁRIOS
# ══════════════════════════════════════════════════════════

@pytest.fixture
def tmp_dirs(tmp_path):
    """
    Cria estrutura de diretórios temporários para testes.
    Simula a estrutura de pastas do projeto.
    """
    dirs = {
        "downloads": tmp_path / "downloads",
        "cortes": tmp_path / "cortes",
        "output": tmp_path / "output",
        "fundos": tmp_path / "fundos",
        "musicas": tmp_path / "musicas",
        "temp_audio": tmp_path / "temp_audio",
        "logs": tmp_path / "logs",
    }

    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    return dirs


@pytest.fixture
def video_fake(tmp_path: Path) -> Path:
    """
    Cria um arquivo de vídeo fake para testes.
    Não é um vídeo real, só para testar manipulação de arquivos.
    """
    video_path = tmp_path / "test_video.mp4"
    video_path.write_bytes(b"FAKE_VIDEO_CONTENT_" * 1000)  # ~20KB
    return video_path


@pytest.fixture
def audio_fake(tmp_path: Path) -> Path:
    """Arquivo de áudio fake para testes."""
    audio_path = tmp_path / "test_audio.mp3"
    audio_path.write_bytes(b"FAKE_AUDIO_CONTENT_" * 1000)  # ~20KB
    return audio_path


# ══════════════════════════════════════════════════════════
# FIXTURES DE CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════

@pytest.fixture
def config_teste(monkeypatch, tmp_path):
    """
    Sobrescreve configuração global para testes.
    Evita usar credenciais reais ou fazer chamadas de API.
    """
    from config import cfg

    # Desabilitar chamadas de API reais
    monkeypatch.setattr(cfg, "chave_anthropic", "sk-ant-test-fake-key-12345678")
    monkeypatch.setattr(cfg, "chave_elevenlabs", "fake-elevenlabs-key-12345678")
    monkeypatch.setattr(cfg, "telegram_token", "123456:ABC-DEF-TEST-TOKEN")
    monkeypatch.setattr(cfg, "telegram_chat_id", "123456789")

    # Usar pastas temporárias
    monkeypatch.setattr(cfg, "pasta_downloads", tmp_path / "downloads")
    monkeypatch.setattr(cfg, "pasta_cortes", tmp_path / "cortes")
    monkeypatch.setattr(cfg, "pasta_prontos", tmp_path / "output")
    monkeypatch.setattr(cfg, "pasta_audio_temp", tmp_path / "temp_audio")
    monkeypatch.setattr(cfg, "pasta_logs", tmp_path / "logs")

    # Criar as pastas
    cfg.criar_pastas()

    return cfg


# ══════════════════════════════════════════════════════════
# FIXTURES DE MOCKS DE API
# ══════════════════════════════════════════════════════════

@pytest.fixture
def mock_anthropic_success(monkeypatch):
    """
    Mock da API Anthropic retornando sucesso.
    Simula resposta válida sem custo real.
    """
    class MockResponse:
        def __init__(self):
            self.content = [type('obj', (), {
                'text': '[{"tipo":"denso","inicio":10.0,"fim":65.0,"titulo":"Teste","gancho":"Gancho teste","motivo":"Teste"}]'
            })]
            self.usage = type('obj', (), {
                'input_tokens': 150,
                'output_tokens': 250
            })

    class MockClient:
        class messages:
            @staticmethod
            def create(*args, **kwargs):
                return MockResponse()

    return MockClient


@pytest.fixture
def mock_subprocess_success(monkeypatch):
    """Mock do subprocess retornando sucesso."""
    class MockProcess:
        returncode = 0
        stdout = '{"format":{"duration":"180.5"}}'
        stderr = ""

    def fake_run(*args, **kwargs):
        return MockProcess()

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    return fake_run


# ══════════════════════════════════════════════════════════
# FIXTURES DE TEMPO
# ══════════════════════════════════════════════════════════

@pytest.fixture
def freeze_time(monkeypatch):
    """
    Congela o tempo para testes determinísticos.
    Útil para testar agendamentos e timestamps.
    """
    from datetime import datetime as dt_original

    class FakeDatetime:
        fixed_time = dt_original(2026, 8, 19, 12, 0, 0)

        @classmethod
        def now(cls, *args, **kwargs):
            return cls.fixed_time

        @classmethod
        def strptime(cls, *args, **kwargs):
            return dt_original.strptime(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(dt_original, name)

    return FakeDatetime


# ══════════════════════════════════════════════════════════
# MARKERS CUSTOMIZADOS
# ══════════════════════════════════════════════════════════

def pytest_configure(config):
    """Registra markers customizados."""
    config.addinivalue_line(
        "markers", "slow: marca testes lentos (mais de 1s)"
    )
    config.addinivalue_line(
        "markers", "integration: testes de integração que tocam múltiplos módulos"
    )
    config.addinivalue_line(
        "markers", "security: testes de segurança e validação de entrada"
    )
    config.addinivalue_line(
        "markers", "unit: testes unitários isolados"
    )
