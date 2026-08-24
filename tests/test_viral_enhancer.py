#!/usr/bin/env python3
"""
Testes para viral_enhancer.py - Features de Viralização
"""

import pytest
from pathlib import Path
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock
from viral_enhancer import (
    adicionar_legendas_virais,
    analisar_hook_score,
    otimizar_cortes_dinamicos,
    validar_video_para_postagem,
    _obter_duracao_video,
    _gerar_ass_viral,
    _segundos_para_ass_time,
    _detectar_movimento,
    _analisar_contraste,
    _verificar_audio,
    _detectar_mudanca_cena,
    _extrair_clip,
    _detectar_cenas,
    _aplicar_zoom_dinamico
)


@pytest.fixture
def video_fake(tmp_path):
    """Cria vídeo fake de 60 segundos."""
    video = tmp_path / "video_teste.mp4"

    # Criar vídeo fake com FFmpeg (60s, 1080x1920, com áudio)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=60:size=1080x1920:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=60",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        str(video)
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        return video
    except Exception as e:
        pytest.skip(f"Não foi possível criar vídeo fake: {e}")


@pytest.fixture
def texto_exemplo():
    """Texto para testes de legendas."""
    return "Jesus Cristo é o Salvador do mundo e traz paz"


# ═══════════════════════════════════════════════════════
#  TESTES - LEGENDAS DINÂMICAS
# ═══════════════════════════════════════════════════════

@pytest.mark.unit
def test_segundos_para_ass_time():
    """Testa conversão de segundos para formato ASS."""
    assert _segundos_para_ass_time(0) == "0:00:00.00"
    assert _segundos_para_ass_time(1.5) == "0:00:01.50"
    assert _segundos_para_ass_time(65.25) == "0:01:05.25"
    assert _segundos_para_ass_time(3661.99) == "1:01:01.99"


@pytest.mark.unit
def test_gerar_ass_viral_bounce(tmp_path, texto_exemplo):
    """Testa geração de arquivo ASS com estilo bounce."""
    output = tmp_path / "legendas.ass"
    palavras = texto_exemplo.split()
    tempo_por_palavra = 0.5

    _gerar_ass_viral(
        palavras,
        tempo_por_palavra,
        output,
        estilo="bounce",
        cor_primaria="yellow",
        cor_secundaria="white"
    )

    # Verificar se arquivo foi criado
    assert output.exists()

    # Verificar conteúdo
    conteudo = output.read_text(encoding="utf-8")
    assert "[Script Info]" in conteudo
    assert "[V4+ Styles]" in conteudo
    assert "[Events]" in conteudo
    assert "Style: Viral" in conteudo
    assert "Jesus" in conteudo
    assert "Cristo" in conteudo
    assert "\\move(" in conteudo  # Efeito bounce


@pytest.mark.unit
def test_gerar_ass_viral_highlight(tmp_path, texto_exemplo):
    """Testa geração de arquivo ASS com estilo highlight."""
    output = tmp_path / "legendas_highlight.ass"
    palavras = texto_exemplo.split()

    _gerar_ass_viral(
        palavras,
        0.5,
        output,
        estilo="highlight",
        cor_primaria="yellow",
        cor_secundaria="white"
    )

    conteudo = output.read_text(encoding="utf-8")
    assert "\\c&H0000FFFF" in conteudo  # Código de cor amarelo
    assert "\\b1" in conteudo  # Bold


@pytest.mark.unit
def test_gerar_ass_viral_karaoke(tmp_path, texto_exemplo):
    """Testa geração de arquivo ASS com estilo karaoke."""
    output = tmp_path / "legendas_karaoke.ass"
    palavras = texto_exemplo.split()

    _gerar_ass_viral(
        palavras,
        0.5,
        output,
        estilo="karaoke",
        cor_primaria="yellow",
        cor_secundaria="white"
    )

    conteudo = output.read_text(encoding="utf-8")
    assert "\\k" in conteudo  # Efeito karaoke


@pytest.mark.integration
@patch("subprocess.run")
def test_obter_duracao_video_sucesso(mock_run, tmp_path):
    """Testa obtenção de duração com sucesso."""
    video = tmp_path / "video.mp4"
    video.touch()

    # Mock do resultado do ffprobe
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = json.dumps({"format": {"duration": "60.5"}})
    mock_run.return_value = mock_result

    duracao = _obter_duracao_video(video)

    assert duracao == 60.5
    mock_run.assert_called_once()


@pytest.mark.integration
@patch("subprocess.run")
def test_obter_duracao_video_erro(mock_run, tmp_path):
    """Testa falha ao obter duração."""
    video = tmp_path / "video.mp4"
    video.touch()

    mock_result = Mock()
    mock_result.returncode = 1
    mock_run.return_value = mock_result

    duracao = _obter_duracao_video(video)

    assert duracao is None


@pytest.mark.slow
@pytest.mark.integration
@patch("subprocess.run")
@patch("viral_enhancer._obter_duracao_video")
def test_adicionar_legendas_virais_sucesso(mock_duracao, mock_run, tmp_path, texto_exemplo):
    """Testa adição de legendas virais com sucesso."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "video_legendado.mp4"

    # Mock de duração
    mock_duracao.return_value = 60.0

    # Mock do FFmpeg
    mock_result = Mock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    sucesso = adicionar_legendas_virais(
        video,
        texto_exemplo,
        output,
        estilo="bounce"
    )

    assert sucesso is True
    mock_duracao.assert_called_once_with(video)

    # Verificar que FFmpeg foi chamado
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert "ffmpeg" in call_args
    assert "-vf" in call_args
    assert "ass=" in " ".join(str(x) for x in call_args)


@pytest.mark.integration
@patch("viral_enhancer._obter_duracao_video")
def test_adicionar_legendas_virais_sem_duracao(mock_duracao, tmp_path, texto_exemplo):
    """Testa falha quando não consegue obter duração."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "video_legendado.mp4"

    mock_duracao.return_value = None

    sucesso = adicionar_legendas_virais(video, texto_exemplo, output)

    assert sucesso is False


# ═══════════════════════════════════════════════════════
#  TESTES - HOOK ANALYZER
# ═══════════════════════════════════════════════════════

@pytest.mark.unit
@patch("subprocess.run")
def test_detectar_movimento_alto(mock_run):
    """Testa detecção de movimento alto."""
    video = Path("video.mp4")

    # Simular muitos frames com movimento
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "Parsed_showinfo\n" * 50  # 50 frames com movimento
    mock_run.return_value = mock_result

    score = _detectar_movimento(video)

    assert score > 0.3  # Acima do threshold


@pytest.mark.unit
@patch("subprocess.run")
def test_detectar_movimento_baixo(mock_run):
    """Testa detecção de movimento baixo."""
    video = Path("video.mp4")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "Parsed_showinfo\n" * 5  # Poucos frames
    mock_run.return_value = mock_result

    score = _detectar_movimento(video)

    assert score < 0.3


@pytest.mark.unit
@patch("subprocess.run")
def test_analisar_contraste_alto(mock_run):
    """Testa análise de contraste alto."""
    video = Path("video.mp4")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "YMIN: 10\nYMAX: 240\n"
    mock_run.return_value = mock_result

    contraste = _analisar_contraste(video)

    assert contraste == 230.0
    assert contraste > 40  # Acima do threshold


@pytest.mark.unit
@patch("subprocess.run")
def test_verificar_audio_presente(mock_run):
    """Testa verificação de áudio presente."""
    video = Path("video.mp4")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "mean_volume: -20.5 dB"
    mock_run.return_value = mock_result

    tem_audio = _verificar_audio(video)

    assert tem_audio is True


@pytest.mark.unit
@patch("subprocess.run")
def test_verificar_audio_ausente(mock_run):
    """Testa verificação de áudio ausente."""
    video = Path("video.mp4")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "mean_volume: -91.0 dB"  # Muito baixo
    mock_run.return_value = mock_result

    tem_audio = _verificar_audio(video)

    assert tem_audio is False


@pytest.mark.unit
@patch("subprocess.run")
def test_detectar_mudanca_cena_presente(mock_run):
    """Testa detecção de mudança de cena."""
    video = Path("video.mp4")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "Parsed_showinfo\nParsed_showinfo\n"  # 2 cenas
    mock_run.return_value = mock_result

    tem_corte = _detectar_mudanca_cena(video)

    assert tem_corte is True


@pytest.mark.integration
@patch("viral_enhancer._extrair_clip")
@patch("viral_enhancer._detectar_movimento")
@patch("viral_enhancer._analisar_contraste")
@patch("viral_enhancer._verificar_audio")
@patch("viral_enhancer._detectar_mudanca_cena")
def test_analisar_hook_score_excelente(
    mock_cena, mock_audio, mock_contraste, mock_movimento, mock_clip, tmp_path
):
    """Testa análise de hook com score excelente (100/100)."""
    video = tmp_path / "video.mp4"
    video.touch()

    # Mock de todos os critérios como positivos
    mock_clip.return_value = True
    mock_movimento.return_value = 0.8  # Alto movimento
    mock_contraste.return_value = 120.0  # Alto contraste
    mock_audio.return_value = True
    mock_cena.return_value = True

    resultado = analisar_hook_score(video)

    assert resultado["score"] == 100
    assert resultado["movimento"] is True
    assert resultado["contraste"] is True
    assert resultado["audio"] is True
    assert resultado["cena"] is True
    assert "Excelente" in resultado["recomendacao"]
    assert "POSTAR" in resultado["recomendacao"]


@pytest.mark.integration
@patch("viral_enhancer._extrair_clip")
@patch("viral_enhancer._detectar_movimento")
@patch("viral_enhancer._analisar_contraste")
@patch("viral_enhancer._verificar_audio")
@patch("viral_enhancer._detectar_mudanca_cena")
def test_analisar_hook_score_fraco(
    mock_cena, mock_audio, mock_contraste, mock_movimento, mock_clip, tmp_path
):
    """Testa análise de hook com score fraco (25/100)."""
    video = tmp_path / "video.mp4"
    video.touch()

    # Apenas 1 critério positivo
    mock_clip.return_value = True
    mock_movimento.return_value = 0.5  # Movimento OK
    mock_contraste.return_value = 20.0  # Baixo contraste
    mock_audio.return_value = False
    mock_cena.return_value = False

    resultado = analisar_hook_score(video)

    assert resultado["score"] == 25
    assert resultado["movimento"] is True
    assert resultado["contraste"] is False
    assert "Hook fraco" in resultado["recomendacao"]
    assert "NÃO POSTAR" in resultado["recomendacao"]


# ═══════════════════════════════════════════════════════
#  TESTES - CORTES DINÂMICOS
# ═══════════════════════════════════════════════════════

@pytest.mark.unit
@patch("subprocess.run")
def test_detectar_cenas(mock_run):
    """Testa detecção de cenas no vídeo."""
    video = Path("video.mp4")

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = """
    pts_time:0.0
    pts_time:2.5
    pts_time:5.0
    pts_time:8.2
    """
    mock_run.return_value = mock_result

    cenas = _detectar_cenas(video)

    assert len(cenas) == 3  # 4 timestamps = 3 intervalos
    assert cenas[0] == (0.0, 2.5)
    assert cenas[1] == (2.5, 5.0)
    assert cenas[2] == (5.0, 8.2)


@pytest.mark.integration
@patch("subprocess.run")
def test_aplicar_zoom_dinamico_sucesso(mock_run, tmp_path):
    """Testa aplicação de zoom dinâmico."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "video_zoom.mp4"

    mock_result = Mock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    sucesso = _aplicar_zoom_dinamico(video, output)

    assert sucesso is True
    assert mock_run.called

    # Verificar filtro zoompan aplicado
    call_args = str(mock_run.call_args)
    assert "zoompan" in call_args


@pytest.mark.integration
@patch("viral_enhancer._detectar_cenas")
@patch("shutil.copy2")
def test_otimizar_cortes_dinamicos_ja_otimizado(mock_copy, mock_cenas, tmp_path):
    """Testa otimização quando vídeo já tem bom ritmo."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "video_otimizado.mp4"

    # Simular cenas curtas (já otimizado)
    mock_cenas.return_value = [
        (0.0, 2.0),
        (2.0, 4.5),
        (4.5, 7.0)
    ]  # Média: 2.5s/cena - bom ritmo

    sucesso = otimizar_cortes_dinamicos(video, output)

    assert sucesso is True
    mock_copy.assert_called_once_with(video, output)


@pytest.mark.integration
@patch("viral_enhancer._detectar_cenas")
@patch("viral_enhancer._aplicar_zoom_dinamico")
def test_otimizar_cortes_dinamicos_precisa_zoom(mock_zoom, mock_cenas, tmp_path):
    """Testa otimização quando precisa aplicar zoom."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "video_otimizado.mp4"

    # Simular cenas longas
    mock_cenas.return_value = [
        (0.0, 8.0),
        (8.0, 15.0)
    ]  # Média: 7.5s/cena - precisa otimizar

    mock_zoom.return_value = True

    sucesso = otimizar_cortes_dinamicos(video, output)

    assert sucesso is True
    mock_zoom.assert_called_once_with(video, output)


# ═══════════════════════════════════════════════════════
#  TESTES - VALIDAÇÃO COMPLETA
# ═══════════════════════════════════════════════════════

@pytest.mark.integration
@patch("viral_enhancer.analisar_hook_score")
@patch("viral_enhancer._obter_duracao_video")
def test_validar_video_para_postagem_aprovado(mock_duracao, mock_hook, tmp_path):
    """Testa validação completa - vídeo aprovado."""
    video = tmp_path / "video.mp4"
    video.touch()

    mock_hook.return_value = {
        "score": 85,
        "movimento": True,
        "contraste": True,
        "audio": True,
        "cena": True,
        "recomendacao": "Excelente"
    }
    mock_duracao.return_value = 65.0  # Duração ideal

    resultado = validar_video_para_postagem(video, hook_minimo=70)

    assert resultado["aprovado"] is True
    assert resultado["hook_score"] == 85
    assert len(resultado["motivos"]) == 2  # Hook + duração
    assert "Hook score: 85/100" in resultado["motivos"][0]
    assert "Duração ideal: 65s" in resultado["motivos"][1]
    assert len(resultado["sugestoes"]) == 0


@pytest.mark.integration
@patch("viral_enhancer.analisar_hook_score")
@patch("viral_enhancer._obter_duracao_video")
def test_validar_video_para_postagem_reprovado(mock_duracao, mock_hook, tmp_path):
    """Testa validação completa - vídeo reprovado."""
    video = tmp_path / "video.mp4"
    video.touch()

    mock_hook.return_value = {
        "score": 45,
        "movimento": False,
        "contraste": True,
        "audio": False,
        "cena": False,
        "recomendacao": "Hook fraco"
    }
    mock_duracao.return_value = 120.0  # Muito longo

    resultado = validar_video_para_postagem(video, hook_minimo=70)

    assert resultado["aprovado"] is False
    assert resultado["hook_score"] == 45
    assert len(resultado["sugestoes"]) > 0
    assert "Hook fraco" in resultado["sugestoes"][0]


# ═══════════════════════════════════════════════════════
#  TESTES - EDGE CASES
# ═══════════════════════════════════════════════════════

@pytest.mark.unit
def test_segundos_para_ass_time_edge_cases():
    """Testa conversão de tempo com edge cases."""
    # Zero
    assert _segundos_para_ass_time(0.0) == "0:00:00.00"

    # Valores decimais pequenos
    assert _segundos_para_ass_time(0.01) == "0:00:00.01"
    assert _segundos_para_ass_time(0.99) == "0:00:00.99"

    # Valores grandes
    assert _segundos_para_ass_time(7200) == "2:00:00.00"


@pytest.mark.unit
def test_gerar_ass_viral_texto_vazio(tmp_path):
    """Testa geração de ASS com lista vazia."""
    output = tmp_path / "vazio.ass"

    _gerar_ass_viral([], 0.5, output, "bounce", "yellow", "white")

    # Deve criar arquivo com headers mas sem eventos
    assert output.exists()
    conteudo = output.read_text(encoding="utf-8")
    assert "[Events]" in conteudo
    assert "Dialogue:" not in conteudo  # Sem eventos


@pytest.mark.integration
@patch("subprocess.run")
def test_extrair_clip_timeout(mock_run, tmp_path):
    """Testa timeout ao extrair clip."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "clip.mp4"

    mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 30)

    sucesso = _extrair_clip(video, output, 0, 3)

    assert sucesso is False


@pytest.mark.integration
@patch("subprocess.run")
def test_obter_duracao_video_timeout(mock_run, tmp_path):
    """Testa timeout ao obter duração."""
    video = tmp_path / "video.mp4"
    video.touch()

    mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 30)

    duracao = _obter_duracao_video(video)

    assert duracao is None


# ═══════════════════════════════════════════════════════
#  TESTES - SEGURANÇA
# ═══════════════════════════════════════════════════════

@pytest.mark.security
def test_validacao_path_injection(tmp_path):
    """Testa proteção contra path injection em legendas."""
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "output.mp4"

    # Tentar injetar path malicioso no texto
    texto_malicioso = "../../etc/passwd; rm -rf /"

    # Não deve crashar ou executar comandos
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=1)
        with patch("viral_enhancer._obter_duracao_video") as mock_dur:
            mock_dur.return_value = 60.0

            sucesso = adicionar_legendas_virais(video, texto_malicioso, output)

            # Deve falhar mas não executar comandos
            assert sucesso is False


@pytest.mark.security
def test_validacao_comando_injection_ass():
    """Testa proteção contra command injection em arquivo ASS."""
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "test.ass"

        # Tentar injetar comandos via texto
        palavras_maliciosas = [
            "normal",
            "'; rm -rf / #",
            "$(whoami)",
            "`cat /etc/passwd`"
        ]

        # Não deve executar comandos
        _gerar_ass_viral(
            palavras_maliciosas,
            0.5,
            output,
            "bounce",
            "yellow",
            "white"
        )

        # Arquivo deve ser criado normalmente
        assert output.exists()

        # Comandos devem estar escapados/literais no ASS
        conteudo = output.read_text(encoding="utf-8")
        assert "rm -rf" in conteudo  # Como texto literal, não executado
        assert "$(whoami)" in conteudo  # Como texto literal


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
