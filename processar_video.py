#!/usr/bin/env python3
"""
=======================================================
  PROCESSADOR DE VÍDEO PARA TIKTOK — Monetização
=======================================================
  Transforma cortes de podcast em conteúdo único:
  - Recodifica (muda fingerprint/hash)
  - Gera legendas automáticas com Whisper (IA)
  - Adiciona marca d'água / logo
  - Ajusta para formato vertical 9:16
  - Aplica filtros visuais para ser "novo" pro algoritmo
=======================================================
  Uso:
    python processar_video.py                    (processa pasta INPUT/)
    python processar_video.py meu_video.mp4      (processa um arquivo)
    python processar_video.py --modelo large     (usa modelo Whisper maior)
=======================================================
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# ─── CONFIGURAÇÕES — edite aqui ─────────────────────────
PASTA_INPUT   = "input"          # pasta com os vídeos originais
PASTA_OUTPUT  = "output"         # pasta onde os vídeos processados serão salvos
PASTA_BACKUP  = "backup"         # pasta onde os originais são movidos após processar

NOME_CANAL    = "@SeuCanal"      # seu @ do TikTok (aparece no vídeo)
COR_LEGENDA   = "white"          # cor do texto da legenda: white, yellow, cyan
COR_BORDA     = "&H00000000"     # cor da borda da legenda (preto transparente = &H00000000)
TAMANHO_FONT  = 18               # tamanho da fonte da legenda (14–22 recomendado)

MODELO_WHISPER = "base"          # tiny | base | small | medium | large
                                 # tiny = mais rápido | large = mais preciso

FORMATO_SAIDA  = "9:16"          # "9:16" (vertical TikTok) | "original" (mantém)
QUALIDADE_CRF  = 23              # qualidade do vídeo: 18=alta, 23=boa, 28=comprimida
VELOCIDADE_ENC = "medium"        # ultrafast | fast | medium | slow

ADICIONAR_LOGO = True            # True = adiciona nome do canal no canto
POSICAO_LOGO   = "top-right"     # top-left | top-right | bottom-left | bottom-right

ADICIONAR_INTRO_AUDIO = False    # True = adiciona 0.5s de silêncio no início (muda hash de áudio)
AJUSTE_PITCH  = True             # True = altera pitch do áudio levemente (mais difícil de detectar)
PITCH_VALOR   = "1.02"           # 1.0 = original | 1.02 = +2% (imperceptível)

IDIOMA_TRANSCRICAO = "pt"        # pt = português | en = inglês | auto = detecta automaticamente
# ─────────────────────────────────────────────────────────


CORES_ASS = {
    "white":  "&H00FFFFFF",
    "yellow": "&H0000FFFF",
    "cyan":   "&H00FFFF00",
    "green":  "&H0000FF00",
}

def log(msg, nivel="INFO"):
    hora = datetime.now().strftime("%H:%M:%S")
    prefixos = {"INFO": "✓", "ERRO": "✗", "AVISO": "⚠", "PROC": "→"}
    print(f"[{hora}] {prefixos.get(nivel,'·')} {msg}")

def verificar_dependencias():
    erros = []
    if not shutil.which("ffmpeg"):
        erros.append("FFmpeg não encontrado. Instale: https://ffmpeg.org/download.html")
    if not shutil.which("ffprobe"):
        erros.append("FFprobe não encontrado (vem junto com FFmpeg).")
    try:
        import whisper
    except ImportError:
        erros.append("Whisper não instalado. Rode: pip install openai-whisper")
    if erros:
        print("\n❌ Dependências faltando:\n")
        for e in erros:
            print(f"   • {e}")
        sys.exit(1)
    log("Dependências OK (FFmpeg + Whisper)")

def obter_info_video(caminho):
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", str(caminho)
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    dados = json.loads(resultado.stdout)
    
    info = {"duracao": 0, "largura": 0, "altura": 0, "fps": 30, "tem_audio": False}
    
    for stream in dados.get("streams", []):
        if stream.get("codec_type") == "video":
            info["largura"] = int(stream.get("width", 0))
            info["altura"] = int(stream.get("height", 0))
            fps_str = stream.get("r_frame_rate", "30/1")
            try:
                num, den = fps_str.split("/")
                info["fps"] = round(int(num) / int(den), 2)
            except:
                info["fps"] = 30
        elif stream.get("codec_type") == "audio":
            info["tem_audio"] = True
    
    info["duracao"] = float(dados.get("format", {}).get("duration", 0))
    return info

def transcrever_audio(caminho_video, pasta_temp):
    """Usa Whisper para gerar legendas automáticas em formato ASS"""
    log(f"Transcrevendo com Whisper ({MODELO_WHISPER})... (pode demorar)", "PROC")
    
    try:
        import whisper
        modelo = whisper.load_model(MODELO_WHISPER)
        
        idioma = None if IDIOMA_TRANSCRICAO == "auto" else IDIOMA_TRANSCRICAO
        
        resultado = modelo.transcribe(
            str(caminho_video),
            language=idioma,
            word_timestamps=True,
            verbose=False
        )
        
        # Gera arquivo ASS com legendas estilizadas
        caminho_ass = pasta_temp / "legendas.ass"
        gerar_ass(resultado["segments"], caminho_ass)
        
        log(f"Transcrição concluída: {len(resultado['segments'])} segmentos")
        return caminho_ass
        
    except Exception as e:
        log(f"Erro na transcrição: {e}", "ERRO")
        return None

def gerar_ass(segmentos, caminho_saida):
    """Gera arquivo de legenda ASS estilizado"""
    
    cor_primaria = CORES_ASS.get(COR_LEGENDA, "&H00FFFFFF")
    
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{TAMANHO_FONT},{cor_primaria},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def segundos_para_ass(s):
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        seg = s % 60
        return f"{h}:{m:02d}:{seg:05.2f}"
    
    linhas = [header]
    for seg in segmentos:
        inicio = segundos_para_ass(seg["start"])
        fim    = segundos_para_ass(seg["end"])
        texto  = seg["text"].strip().replace("\n", " ")
        # Quebra linhas longas
        if len(texto) > 40:
            meio = len(texto) // 2
            espaco = texto.rfind(" ", 0, meio)
            if espaco > 0:
                texto = texto[:espaco] + r"\N" + texto[espaco+1:]
        linhas.append(f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}")
    
    with open(caminho_saida, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

def processar_video(caminho_entrada, caminho_saida):
    """Pipeline completo de transformação do vídeo"""
    
    caminho_entrada = Path(caminho_entrada)
    caminho_saida   = Path(caminho_saida)
    
    if not caminho_entrada.exists():
        log(f"Arquivo não encontrado: {caminho_entrada}", "ERRO")
        return False
    
    log(f"Processando: {caminho_entrada.name}", "PROC")
    
    info = obter_info_video(caminho_entrada)
    log(f"Vídeo: {info['largura']}x{info['altura']} | {info['fps']} fps | {info['duracao']:.1f}s")
    
    with tempfile.TemporaryDirectory() as pasta_temp:
        pasta_temp = Path(pasta_temp)
        
        # ── Etapa 1: Transcrição ──────────────────────────
        caminho_ass = None
        if info["tem_audio"]:
            caminho_ass = transcrever_audio(caminho_entrada, pasta_temp)
        
        # ── Etapa 2: Montar filtros FFmpeg ────────────────
        filtros_video = []
        filtros_audio = []
        
        # Ajustar para 9:16 (vertical TikTok)
        if FORMATO_SAIDA == "9:16":
            larg_alvo = 1080
            alt_alvo  = 1920
            
            if info["largura"] > 0 and info["altura"] > 0:
                ratio_atual = info["largura"] / info["altura"]
                ratio_alvo  = larg_alvo / alt_alvo
                
                if abs(ratio_atual - ratio_alvo) > 0.05:
                    # Coloca o vídeo no centro com fundo preto
                    filtros_video.append(
                        f"scale={larg_alvo}:{alt_alvo}:force_original_aspect_ratio=decrease,"
                        f"pad={larg_alvo}:{alt_alvo}:(ow-iw)/2:(oh-ih)/2:black"
                    )
                else:
                    filtros_video.append(f"scale={larg_alvo}:{alt_alvo}")
        
        # Legenda automática
        if caminho_ass and caminho_ass.exists():
            ass_escaped = str(caminho_ass).replace("\\", "/").replace(":", "\\:")
            filtros_video.append(f"ass='{ass_escaped}'")
            log("Legendas adicionadas ao vídeo")
        
        # Logo / nome do canal
        if ADICIONAR_LOGO and NOME_CANAL:
            posicoes = {
                "top-left":     "x=20:y=20",
                "top-right":    "x=w-tw-20:y=20",
                "bottom-left":  "x=20:y=h-th-20",
                "bottom-right": "x=w-tw-20:y=h-th-20",
            }
            pos = posicoes.get(POSICAO_LOGO, "x=w-tw-20:y=20")
            nome_escaped = NOME_CANAL.replace("@", "\\@")
            filtros_video.append(
                f"drawtext=text='{nome_escaped}':fontcolor=white:fontsize=24:"
                f"box=1:boxcolor=black@0.5:boxborderw=6:{pos}"
            )
            log(f"Logo '{NOME_CANAL}' adicionado ({POSICAO_LOGO})")
        
        # Pitch do áudio (dificulta detecção por fingerprint de áudio)
        if AJUSTE_PITCH and info["tem_audio"]:
            filtros_audio.append(f"atempo={PITCH_VALOR}")
            # Corrige o pitch para não mudar o tom (só a velocidade)
            filtros_audio.append(f"asetrate=44100*{PITCH_VALOR},aresample=44100")
            log(f"Ajuste de pitch aplicado ({PITCH_VALOR}x)")
        
        # Silêncio no início (muda hash de áudio)
        if ADICIONAR_INTRO_AUDIO and info["tem_audio"]:
            filtros_audio.append("adelay=500|500")
        
        # ── Etapa 3: Montar comando FFmpeg ────────────────
        cmd = ["ffmpeg", "-y", "-i", str(caminho_entrada)]
        
        # Filtros de vídeo
        vf_str = ",".join(filtros_video) if filtros_video else None
        af_str = ",".join(filtros_audio) if filtros_audio else None
        
        if vf_str:
            cmd += ["-vf", vf_str]
        if af_str:
            cmd += ["-af", af_str]
        
        # Codec e qualidade
        cmd += [
            "-c:v", "libx264",
            "-crf", str(QUALIDADE_CRF),
            "-preset", VELOCIDADE_ENC,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",  # otimiza para streaming
        ]
        
        if info["tem_audio"]:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        
        # Metadados zerados (remove fingerprint de metadados)
        cmd += [
            "-metadata", "title=",
            "-metadata", "comment=",
            "-metadata", "encoder=",
        ]
        
        cmd.append(str(caminho_saida))
        
        # ── Etapa 4: Executar ─────────────────────────────
        log("Renderizando vídeo final...", "PROC")
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if resultado.returncode != 0:
            log(f"Erro no FFmpeg:\n{resultado.stderr[-500:]}", "ERRO")
            return False
        
        tamanho = caminho_saida.stat().st_size / (1024*1024)
        log(f"✅ Salvo: {caminho_saida.name} ({tamanho:.1f} MB)")
        return True

def processar_pasta():
    """Processa todos os vídeos da pasta input/"""
    
    pasta_in  = Path(PASTA_INPUT)
    pasta_out = Path(PASTA_OUTPUT)
    pasta_bkp = Path(PASTA_BACKUP)
    
    for pasta in [pasta_in, pasta_out, pasta_bkp]:
        pasta.mkdir(exist_ok=True)
    
    extensoes = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    videos = [f for f in pasta_in.iterdir() if f.suffix.lower() in extensoes]
    
    if not videos:
        log(f"Nenhum vídeo encontrado em '{PASTA_INPUT}/'", "AVISO")
        log(f"Coloque seus vídeos na pasta '{PASTA_INPUT}/' e rode novamente.")
        return
    
    log(f"Encontrados {len(videos)} vídeo(s) para processar")
    print("─" * 50)
    
    sucessos = 0
    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] {video.name}")
        
        nome_saida = f"pronto_{video.stem}_{datetime.now().strftime('%H%M%S')}.mp4"
        caminho_saida = pasta_out / nome_saida
        
        if processar_video(video, caminho_saida):
            # Move original para backup
            shutil.move(str(video), str(pasta_bkp / video.name))
            log(f"Original movido para '{PASTA_BACKUP}/'")
            sucessos += 1
        else:
            log(f"Falhou: {video.name}", "ERRO")
        
        print("─" * 50)
    
    print(f"\n🎉 Concluído: {sucessos}/{len(videos)} vídeos processados")
    print(f"   📁 Vídeos prontos em: {pasta_out.resolve()}")

def main():
    global MODELO_WHISPER

    parser = argparse.ArgumentParser(
        description="Processador de vídeos para TikTok — monetização"
    )
    parser.add_argument(
        "arquivo", nargs="?",
        help="Arquivo de vídeo específico (opcional)"
    )
    parser.add_argument(
        "--modelo", default=MODELO_WHISPER,
        choices=["tiny", "base", "small", "medium", "large"],
        help="Modelo Whisper para transcrição"
    )
    args = parser.parse_args()

    # Sobrescreve configuração se passado via argumento
    MODELO_WHISPER = args.modelo
    
    print("\n" + "═" * 50)
    print("  PROCESSADOR DE VÍDEO — TIKTOK MONETIZAÇÃO")
    print("═" * 50 + "\n")
    
    verificar_dependencias()
    
    if args.arquivo:
        # Modo arquivo único
        entrada = Path(args.arquivo)
        saida   = Path(PASTA_OUTPUT)
        saida.mkdir(exist_ok=True)
        nome_saida = f"pronto_{entrada.stem}_{datetime.now().strftime('%H%M%S')}.mp4"
        processar_video(entrada, saida / nome_saida)
    else:
        # Modo pasta
        processar_pasta()

if __name__ == "__main__":
    main()