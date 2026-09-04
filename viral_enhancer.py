#!/usr/bin/env python3
"""
=======================================================
  VIRAL ENHANCER — Otimizador de Engajamento para Shorts
=======================================================
  Módulo focado em maximizar viralização de conteúdo católico:

  1. LEGENDAS DINÂMICAS - Palavra-por-palavra com animação
  2. HOOK ANALYZER - Score 0-100 dos primeiros 3 segundos
  3. CORTES DINÂMICOS - Ritmo de 2-3s para alta retenção

  Aumento esperado de engajamento: +40-60%

  Uso:
    from viral_enhancer import adicionar_legendas_virais, analisar_hook_score

    # Adicionar legendas animadas
    adicionar_legendas_virais(video_path, audio_path, output_path)

    # Analisar hook
    score = analisar_hook_score(video_path)
    if score > 70:
        postar_video()
=======================================================
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import cfg
from logger_setup import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════════════════════
#  1. LEGENDAS DINÂMICAS PALAVRA-POR-PALAVRA
# ═══════════════════════════════════════════════════════


def adicionar_legendas_virais(
    video_path: Path,
    texto: str,
    output_path: Path,
    estilo: str = "bounce",
    cor_primaria: str = "yellow",
    cor_secundaria: str = "white",
) -> bool:
    """
    Adiciona legendas animadas palavra-por-palavra estilo viral.

    Args:
        video_path: Caminho do vídeo de entrada
        texto: Texto completo a ser legendado
        output_path: Caminho do vídeo de saída
        estilo: 'bounce' (pula), 'highlight' (destaque), 'karaoke' (palavra-a-palavra)
        cor_primaria: Cor da palavra ativa (amarelo viral)
        cor_secundaria: Cor das demais palavras

    Returns:
        True se sucesso, False se erro
    """
    try:
        logger.info(f"Gerando legendas virais: {estilo}")

        # Obter duração do vídeo
        duracao = _obter_duracao_video(video_path)
        if not duracao:
            logger.error("Não foi possível obter duração do vídeo")
            return False

        # Dividir texto em palavras
        palavras = texto.split()
        num_palavras = len(palavras)

        # Calcular timing por palavra
        tempo_por_palavra = duracao / num_palavras

        # Gerar arquivo ASS com animações
        ass_path = video_path.parent / f"{video_path.stem}_legendas.ass"
        _gerar_ass_viral(
            palavras, tempo_por_palavra, ass_path, estilo, cor_primaria, cor_secundaria
        )

        # Aplicar legendas com FFmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"ass={ass_path}",
            "-c:a",
            "copy",
            "-preset",
            cfg.velocidade_enc,
            "-crf",
            str(cfg.qualidade_crf),
            str(output_path),
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffmpeg_encode
        )

        if result.returncode == 0:
            logger.info(f"✓ Legendas virais adicionadas: {output_path.name}")
            # Limpar arquivo temporário
            ass_path.unlink(missing_ok=True)
            return True
        else:
            logger.error(f"Erro ao adicionar legendas: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Timeout ao adicionar legendas")
        return False
    except Exception as e:
        logger.error(f"Erro ao gerar legendas virais: {e}")
        return False


def _obter_duracao_video(video_path: Path) -> Optional[float]:
    """Obtém duração do vídeo em segundos."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffprobe
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        return None

    except Exception as e:
        logger.error(f"Erro ao obter duração: {e}")
        return None


def _gerar_ass_viral(
    palavras: List[str],
    tempo_por_palavra: float,
    output_path: Path,
    estilo: str,
    cor_primaria: str,
    cor_secundaria: str,
) -> None:
    """
    Gera arquivo ASS com animações palavra-por-palavra.

    Estilos disponíveis:
    - bounce: Palavra pula quando aparece (MAIS VIRAL)
    - highlight: Palavra muda de cor
    - karaoke: Palavra aparece progressivamente
    """
    from constantes import CORES_ASS

    # Converter nomes de cores para código ASS
    cor_pri = CORES_ASS.get(cor_primaria, CORES_ASS["yellow"])
    cor_sec = CORES_ASS.get(cor_secundaria, CORES_ASS["white"])

    # Header ASS
    ass_content = f"""[Script Info]
Title: Legendas Virais
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Viral,Arial Black,80,{cor_pri},{cor_sec},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,10,10,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Gerar eventos para cada palavra
    tempo_atual = 0.0
    grupo_palavras = []

    for i, palavra in enumerate(palavras):
        inicio = tempo_atual
        fim = tempo_atual + tempo_por_palavra

        # Formatar timestamp ASS (H:MM:SS.CS)
        start_time = _segundos_para_ass_time(inicio)
        end_time = _segundos_para_ass_time(fim)

        # Aplicar efeito baseado no estilo
        if estilo == "bounce":
            # Efeito de pulo (move de baixo para cima)
            texto = f"{{\\move(540,1100,540,1000,0,{int(tempo_por_palavra*100)})}}{{\\c{cor_pri}}}{palavra}"
        elif estilo == "highlight":
            # Destaque simples mudando cor
            texto = f"{{\\c{cor_pri}}}{{\\b1}}{palavra}{{\\b0}}"
        else:  # karaoke
            # Efeito karaoke (progressivo)
            texto = f"{{\\k{int(tempo_por_palavra*100)}}}{palavra}"

        # Adicionar palavra ao grupo (máx 4 palavras na tela)
        grupo_palavras.append((start_time, end_time, texto))

        # Quando tiver 4 palavras ou for a última, criar linha
        if len(grupo_palavras) == 4 or i == len(palavras) - 1:
            # Juntar palavras do grupo
            texto_grupo = " ".join([t for _, _, t in grupo_palavras])
            start_grupo = grupo_palavras[0][0]
            end_grupo = grupo_palavras[-1][1]

            ass_content += (
                f"Dialogue: 0,{start_grupo},{end_grupo},Viral,,0,0,0,,{texto_grupo}\n"
            )
            grupo_palavras = []

        tempo_atual = fim

    # Salvar arquivo
    output_path.write_text(ass_content, encoding="utf-8")
    logger.info(f"Arquivo ASS gerado: {output_path.name}")


def _segundos_para_ass_time(segundos: float) -> str:
    """Converte segundos para formato ASS (H:MM:SS.CS)."""
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    segs = int(segundos % 60)
    centesimos = int(round((segundos % 1) * 100))
    return f"{horas}:{minutos:02d}:{segs:02d}.{centesimos:02d}"


# ═══════════════════════════════════════════════════════
#  2. HOOK ANALYZER - Analisa Primeiros 3 Segundos
# ═══════════════════════════════════════════════════════


def analisar_hook_score(video_path: Path) -> Dict[str, any]:
    """
    Analisa os primeiros 3 segundos e retorna score 0-100.

    Critérios:
    - Movimento detectado: +25 pontos
    - Contraste visual alto: +25 pontos
    - Áudio presente e claro: +25 pontos
    - Mudança de cena: +25 pontos

    Returns:
        {
            "score": 85,
            "movimento": True,
            "contraste": True,
            "audio": True,
            "cena": True,
            "recomendacao": "Excelente hook! Postar."
        }
    """
    try:
        logger.info(f"Analisando hook: {video_path.name}")

        score = 0
        detalhes = {
            "movimento": False,
            "contraste": False,
            "audio": False,
            "cena": False,
        }

        # Extrair primeiros 3 segundos
        clip_path = video_path.parent / f"{video_path.stem}_hook_test.mp4"
        _extrair_clip(video_path, clip_path, 0, 3)

        # 1. Detectar movimento (usando ffmpeg com filtro)
        movimento_score = _detectar_movimento(clip_path)
        if movimento_score > 0.3:  # threshold
            score += 25
            detalhes["movimento"] = True
            logger.info(f"✓ Movimento detectado: {movimento_score:.2f}")

        # 2. Analisar contraste
        contraste_score = _analisar_contraste(clip_path)
        if contraste_score > 40:  # threshold
            score += 25
            detalhes["contraste"] = True
            logger.info(f"✓ Contraste alto: {contraste_score:.1f}")

        # 3. Verificar presença de áudio
        audio_presente = _verificar_audio(clip_path)
        if audio_presente:
            score += 25
            detalhes["audio"] = True
            logger.info("✓ Áudio presente")

        # 4. Detectar mudança de cena
        tem_corte = _detectar_mudanca_cena(clip_path)
        if tem_corte:
            score += 25
            detalhes["cena"] = True
            logger.info("✓ Mudança de cena detectada")

        # Limpar arquivo temporário
        clip_path.unlink(missing_ok=True)

        # Gerar recomendação
        if score >= 75:
            recomendacao = "✅ Excelente hook! POSTAR AGORA."
        elif score >= 50:
            recomendacao = "⚠️ Hook médio. Considerar melhorias."
        else:
            recomendacao = "❌ Hook fraco. NÃO POSTAR - refazer primeiros 3s."

        resultado = {"score": score, **detalhes, "recomendacao": recomendacao}

        logger.info(f"Hook Score: {score}/100 - {recomendacao}")
        return resultado

    except Exception as e:
        logger.error(f"Erro ao analisar hook: {e}")
        return {"score": 0, "erro": str(e)}


def _extrair_clip(
    video_path: Path, output_path: Path, inicio: float, duracao: float
) -> bool:
    """Extrai clip de X segundos do vídeo."""
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-ss",
            str(inicio),
            "-t",
            str(duracao),
            "-c",
            "copy",
            str(output_path),
        ]

        result = subprocess.run(
            cmd, capture_output=True, timeout=cfg.timeout_ffmpeg_corte
        )

        return result.returncode == 0

    except Exception as e:
        logger.error(f"Erro ao extrair clip: {e}")
        return False


def _detectar_movimento(video_path: Path) -> float:
    """
    Detecta movimento usando filtro select do FFmpeg.
    Retorna score 0.0-1.0 (quanto maior, mais movimento).
    """
    try:
        # Usar filtro select com motion vectors
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            "select='gt(scene,0.1)',showinfo",
            "-f",
            "null",
            "-",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffprobe
        )

        # Contar frames com movimento no stderr
        movimento_count = result.stderr.count("Parsed_showinfo")

        # Normalizar (3s a 30fps = ~90 frames)
        movimento_ratio = movimento_count / 90.0
        return min(movimento_ratio, 1.0)

    except Exception as e:
        logger.warning(f"Erro ao detectar movimento: {e}")
        return 0.0


def _analisar_contraste(video_path: Path) -> float:
    """
    Analisa contraste usando filtro signalstats do FFmpeg.
    Retorna valor 0-100 (quanto maior, melhor contraste).
    """
    try:
        cmd = ["ffmpeg", "-i", str(video_path), "-vf", "signalstats", "-f", "null", "-"]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffprobe
        )

        # Extrair YMIN e YMAX do stderr
        ymin_match = re.search(r"YMIN:\s*(\d+)", result.stderr)
        ymax_match = re.search(r"YMAX:\s*(\d+)", result.stderr)

        if ymin_match and ymax_match:
            ymin = int(ymin_match.group(1))
            ymax = int(ymax_match.group(1))
            contraste = ymax - ymin
            return float(contraste)

        return 0.0

    except Exception as e:
        logger.warning(f"Erro ao analisar contraste: {e}")
        return 0.0


def _verificar_audio(video_path: Path) -> bool:
    """Verifica se vídeo tem áudio com volume adequado."""
    try:
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffprobe
        )

        # Verificar mean_volume (se > -50dB, tem áudio)
        volume_match = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", result.stderr)

        if volume_match:
            volume = float(volume_match.group(1))
            # Volume > -50dB indica áudio presente
            return volume > -50.0

        return False

    except Exception as e:
        logger.warning(f"Erro ao verificar áudio: {e}")
        return False


def _detectar_mudanca_cena(video_path: Path) -> bool:
    """Detecta se há mudança de cena nos primeiros 3s."""
    try:
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            "select='gt(scene,0.4)',showinfo",
            "-f",
            "null",
            "-",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffprobe
        )

        # Se encontrou pelo menos 1 mudança de cena
        cenas = result.stderr.count("Parsed_showinfo")
        return cenas > 0

    except Exception as e:
        logger.warning(f"Erro ao detectar cenas: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  3. CORTES DINÂMICOS - Ritmo 2-3s
# ═══════════════════════════════════════════════════════


def otimizar_cortes_dinamicos(
    video_path: Path, output_path: Path, ritmo_segundos: float = 2.5
) -> bool:
    """
    Otimiza vídeo para ritmo dinâmico de 2-3s por cena.

    Se o vídeo tem cenas muito longas (>3s), aplica zoom/pan
    para manter interesse visual.

    Args:
        video_path: Vídeo de entrada
        output_path: Vídeo de saída otimizado
        ritmo_segundos: Tempo ideal por "momento visual"

    Returns:
        True se sucesso
    """
    try:
        logger.info("Otimizando ritmo do vídeo para 2-3s por cena")

        # Detectar cenas existentes
        cenas = _detectar_cenas(video_path)

        if not cenas:
            logger.warning("Não foi possível detectar cenas, aplicando zoom padrão")
            return _aplicar_zoom_dinamico(video_path, output_path)

        # Se já tem bom ritmo (cenas curtas), não precisa otimizar
        duracao_media = sum([c[1] - c[0] for c in cenas]) / len(cenas)

        if duracao_media <= 3.5:
            logger.info(f"✓ Ritmo já otimizado (média {duracao_media:.1f}s/cena)")
            # Apenas copiar
            shutil.copy2(video_path, output_path)
            return True

        # Aplicar zoom/pan em cenas longas
        logger.info(f"Aplicando zoom dinâmico (cenas médias: {duracao_media:.1f}s)")
        return _aplicar_zoom_dinamico(video_path, output_path)

    except Exception as e:
        logger.error(f"Erro ao otimizar cortes: {e}")
        return False


def _detectar_cenas(video_path: Path) -> List[Tuple[float, float]]:
    """
    Detecta mudanças de cena usando FFmpeg.
    Retorna lista de tuplas (inicio, fim) em segundos.
    """
    try:
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            "select='gt(scene,0.3)',showinfo",
            "-f",
            "null",
            "-",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=cfg.timeout_ffprobe
        )

        # Extrair timestamps das cenas
        cenas = []
        for line in result.stderr.split("\n"):
            if "pts_time:" in line:
                match = re.search(r"pts_time:(\d+\.?\d*)", line)
                if match:
                    timestamp = float(match.group(1))
                    cenas.append(timestamp)

        # Converter para tuplas (inicio, fim)
        if cenas:
            intervalos = []
            for i in range(len(cenas) - 1):
                intervalos.append((cenas[i], cenas[i + 1]))
            return intervalos

        return []

    except Exception as e:
        logger.warning(f"Erro ao detectar cenas: {e}")
        return []


def _aplicar_zoom_dinamico(video_path: Path, output_path: Path) -> bool:
    """
    Aplica zoom suave e pan para criar dinamismo visual.
    Efeito "Ken Burns" - comum em vídeos virais.
    """
    try:
        # Filtro de zoom progressivo (1x a 1.2x) com pan suave
        filtro = (
            "zoompan=z='min(zoom+0.0015,1.2)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "s=1080x1920:fps=30"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            filtro,
            "-c:a",
            "copy",
            "-preset",
            cfg.velocidade_enc,
            "-crf",
            str(cfg.qualidade_crf),
            str(output_path),
        ]

        result = subprocess.run(
            cmd, capture_output=True, timeout=cfg.timeout_ffmpeg_encode
        )

        if result.returncode == 0:
            logger.info("✓ Zoom dinâmico aplicado")
            return True
        else:
            logger.error("Erro ao aplicar zoom dinâmico")
            return False

    except Exception as e:
        logger.error(f"Erro ao aplicar zoom: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  UTILITÁRIOS
# ═══════════════════════════════════════════════════════


def validar_video_para_postagem(
    video_path: Path, hook_minimo: int = 70
) -> Dict[str, any]:
    """
    Validação completa antes de postar.

    Returns:
        {
            "aprovado": True/False,
            "hook_score": 85,
            "motivos": ["Hook excelente", "Legendas OK"],
            "sugestoes": []
        }
    """
    resultado = {"aprovado": False, "hook_score": 0, "motivos": [], "sugestoes": []}

    # 1. Analisar hook
    hook_analise = analisar_hook_score(video_path)
    resultado["hook_score"] = hook_analise.get("score", 0)

    if resultado["hook_score"] >= hook_minimo:
        resultado["motivos"].append(f"✓ Hook score: {resultado['hook_score']}/100")
    else:
        resultado["sugestoes"].append(
            f"Hook fraco ({resultado['hook_score']}/100). Melhorar primeiros 3s."
        )
        return resultado

    # 2. Verificar duração (ideal: 50-90s)
    duracao = _obter_duracao_video(video_path)
    if duracao and 50 <= duracao <= 90:
        resultado["motivos"].append(f"✓ Duração ideal: {duracao:.0f}s")
    else:
        resultado["sugestoes"].append(
            f"Duração fora do ideal: {duracao:.0f}s (recomendado: 50-90s)"
        )

    # Se chegou aqui, está aprovado
    resultado["aprovado"] = resultado["hook_score"] >= hook_minimo

    return resultado


# ═══════════════════════════════════════════════════════
#  CLI para testes
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Viral Enhancer - Testes")
    parser.add_argument("--video", type=str, help="Caminho do vídeo")
    parser.add_argument("--hook", action="store_true", help="Analisar hook")
    parser.add_argument("--legendas", type=str, help="Texto para legendas")
    parser.add_argument("--validar", action="store_true", help="Validação completa")

    args = parser.parse_args()

    if not args.video:
        print("❌ Use --video para especificar o arquivo")
        sys.exit(1)

    video_path = Path(args.video)

    if not video_path.exists():
        print(f"❌ Arquivo não encontrado: {video_path}")
        sys.exit(1)

    if args.hook:
        print("\n🎯 Analisando Hook...")
        resultado = analisar_hook_score(video_path)
        print(f"\n{'='*50}")
        print(f"HOOK SCORE: {resultado['score']}/100")
        print(f"{'='*50}")
        print(f"Movimento: {'✓' if resultado['movimento'] else '✗'}")
        print(f"Contraste: {'✓' if resultado['contraste'] else '✗'}")
        print(f"Áudio:     {'✓' if resultado['audio'] else '✗'}")
        print(f"Cena:      {'✓' if resultado['cena'] else '✗'}")
        print(f"\n{resultado['recomendacao']}\n")

    elif args.legendas:
        print("\n📝 Adicionando Legendas Virais...")
        output = video_path.parent / f"{video_path.stem}_legendas.mp4"
        sucesso = adicionar_legendas_virais(video_path, args.legendas, output)
        if sucesso:
            print(f"✅ Legendas adicionadas: {output}")
        else:
            print("❌ Erro ao adicionar legendas")

    elif args.validar:
        print("\n✅ Validação Completa...")
        resultado = validar_video_para_postagem(video_path)
        print(f"\n{'='*50}")
        print(f"APROVADO: {'✅ SIM' if resultado['aprovado'] else '❌ NÃO'}")
        print(f"{'='*50}")
        print("\nMotivos:")
        for m in resultado["motivos"]:
            print(f"  {m}")
        if resultado["sugestoes"]:
            print("\nSugestões de Melhoria:")
            for s in resultado["sugestoes"]:
                print(f"  ⚠️ {s}")
        print()
