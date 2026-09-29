"""Testes do pipeline atual de geração de conteúdo."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _resposta_ia(dados: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text=json.dumps(dados, ensure_ascii=False))],
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("funcao", "argumento", "formato"),
    [
        ("ia_gerar_reflexao", "Tecnologia", "reflexao"),
        ("ia_gerar_historia", "Davi e Golias", "historia"),
        ("ia_gerar_versiculo", "João 3:16", "versiculo"),
    ],
)
def test_geradores_ia_usam_resposta_real_da_api(funcao, argumento, formato, config_teste):
    """As três entradas públicas atuais devem normalizar a resposta da IA."""
    import gerador_conteudo

    dados = {
        "roteiro": "Texto de teste para narração.",
        "titulo_yt": "Título de teste",
        "titulo_tiktok": "Título curto",
        "descricao": "Descrição",
        "hashtags": ["#teste"],
    }
    with patch.object(gerador_conteudo, "chamar_anthropic", return_value=_resposta_ia(dados)):
        resultado = getattr(gerador_conteudo, funcao)(argumento, duracao=(30, 40))

    assert resultado["roteiro"] == dados["roteiro"]
    assert resultado["formato"] == formato
    assert resultado["custo_usd"] > 0
    assert resultado["duracao_alvo"] == (30, 40)


@pytest.mark.unit
def test_gerador_ia_propaga_resposta_invalida(config_teste):
    """JSON inválido deve continuar explícito para o chamador tratar."""
    import gerador_conteudo

    resposta = SimpleNamespace(
        content=[SimpleNamespace(text="não é json")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with patch.object(gerador_conteudo, "chamar_anthropic", return_value=resposta):
        with pytest.raises(json.JSONDecodeError):
            gerador_conteudo.ia_gerar_reflexao("Tema", duracao=(30, 40))


@pytest.mark.unit
@patch("gerador_conteudo.requests.post")
def test_gerar_audio_sucesso(mock_post, config_teste, tmp_path):
    from gerador_conteudo import gerar_audio

    resposta = MagicMock(status_code=200)
    resposta.iter_content.return_value = [b"fake_audio_data"]
    mock_post.return_value = resposta
    destino = tmp_path / "audio.mp3"

    assert gerar_audio("Texto de teste", destino) is True
    assert destino.exists()


@pytest.mark.unit
@patch("gerador_conteudo.requests.post")
def test_gerar_audio_falha_api(mock_post, config_teste, tmp_path):
    from gerador_conteudo import gerar_audio

    mock_post.return_value = MagicMock(status_code=500, text="erro")
    assert gerar_audio("Texto de teste", tmp_path / "audio.mp3") is False


@pytest.mark.unit
def test_montar_video_trata_falha_do_ffmpeg(tmp_path):
    from gerador_conteudo import montar_video

    audio = tmp_path / "audio.mp3"
    fundo = tmp_path / "fundo.mp4"
    audio.write_bytes(b"audio")
    fundo.write_bytes(b"video")
    dados = {"roteiro": "Texto", "titulo_yt": "Título", "caminho_fundo": str(fundo)}

    resultado = (None, None)
    with patch("gerador_conteudo.subprocess.run", side_effect=RuntimeError("ffmpeg")):
        resultado = montar_video(dados, audio, tmp_path)
    assert resultado == (None, None)


@pytest.mark.unit
def test_gerar_legendas_atual_usa_utilitario(tmp_path):
    from utils import gerar_ass_de_roteiro

    destino = tmp_path / "legendas.ass"
    gerar_ass_de_roteiro("Texto para legenda.", 5.0, destino)
    assert destino.exists()
    assert "[Script Info]" in destino.read_text(encoding="utf-8")


@pytest.mark.unit
def test_gerar_video_formato_invalido():
    from gerador_conteudo import gerar_video

    assert gerar_video("formato-inexistente") == (None, None)
