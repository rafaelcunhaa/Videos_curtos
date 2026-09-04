#!/usr/bin/env python3
"""
Constantes centralizadas do projeto.
Evita duplicação de valores hardcoded em múltiplos arquivos.
"""

# ── Cores ASS para legendas ──────────────────────────────
# Usado em youtube_para_shorts.py, processar_video.py, gerador_conteudo.py
CORES_ASS = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00"}

# ── Taxa de Câmbio ───────────────────────────────────────
# Conversão USD → BRL para exibição de custos
# Atualizar periodicamente ou integrar com API de câmbio
TAXA_CAMBIO_USD_BRL = 5.60  # última atualização: 2026-08-19

# ── Limites de Rate Limiting ─────────────────────────────
# Aplicados no servidor FastAPI para prevenir abuso
RATE_LIMIT_GERAR_VIDEOS = {"max_requests": 5, "window_seconds": 3600}  # 1 hora

RATE_LIMIT_YOUTUBE_PROCESSAR = {"max_requests": 10, "window_seconds": 3600}  # 1 hora

RATE_LIMIT_LOCAL_UPLOAD = {"max_requests": 20, "window_seconds": 3600}  # 1 hora

# ── Extensões de Vídeo Suportadas ────────────────────────
EXTENSOES_VIDEO_VALIDAS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}

# ── Buffer de Logs SSE ────────────────────────────────────
MAX_LOGS_BUFFER = 500  # número máximo de logs mantidos em memória para streaming

# ── Limites do YouTube ────────────────────────────────────
YOUTUBE_MAX_TITULO = 100  # caracteres
YOUTUBE_MAX_DESCRICAO = 5000  # caracteres
YOUTUBE_MAX_TAGS = 15  # tags por vídeo

# ── Limites do TikTok ─────────────────────────────────────
TIKTOK_MAX_TITULO = 60  # caracteres
TIKTOK_MAX_HASHTAGS = 10  # hashtags por vídeo

# ── Chunk Size para Upload ───────────────────────────────
UPLOAD_CHUNK_SIZE_MB = 10  # MB por chunk no upload do YouTube
UPLOAD_CHUNK_SIZE_BYTES = UPLOAD_CHUNK_SIZE_MB * 1024 * 1024

# ── Durações de Vídeo ─────────────────────────────────────
# Limites globais (aplicados quando formato específico não definido)
DURACAO_MIN_GLOBAL = 30  # segundos
DURACAO_MAX_GLOBAL = 59  # segundos

# ── Timeouts de Conexão ───────────────────────────────────
TIMEOUT_HTTP_DEFAULT = 10.0  # segundos - requests HTTP gerais
TIMEOUT_TELEGRAM_API = 10.0  # segundos - envio de notificações
TIMEOUT_YOUTUBE_UPLOAD = 600  # segundos - upload de vídeo pode ser lento

# ── Banco de Dados ────────────────────────────────────────
BANCO_TIMEOUT = 10  # segundos - timeout de conexão SQLite
BANCO_ARQUIVO_NOME = "banco_shorts.db"

# ── Validação de Status ───────────────────────────────────
STATUS_CORTE_VALIDOS = {"pronto", "agendado", "postado", "erro"}

# ── Regex para Validação ──────────────────────────────────
YOUTUBE_URL_REGEX = r"^https?://(www\.)?(youtube\.com|youtu\.be)/.+"
