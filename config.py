#!/usr/bin/env python3
"""
Configuração centralizada — lê do arquivo .env automaticamente.
Edite o arquivo .env na raiz do projeto (nunca hardcode credenciais).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Carrega o .env automaticamente se existir
try:
    from dotenv import load_dotenv

    load_dotenv(
        override=False
    )  # override=False: variável de ambiente do sistema tem prioridade
except ImportError:
    pass  # dotenv opcional — funciona sem ele se as vars já estiverem no ambiente


@dataclass
class Config:
    # ── API ───────────────────────────────────────────
    chave_anthropic: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    chave_elevenlabs: str = field(
        default_factory=lambda: os.getenv("ELEVENLABS_API_KEY", "")
    )
    telegram_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )
    modelo_claude: str = field(
        default_factory=lambda: os.getenv(
            "ANTHROPIC_MODEL", "claude-sonnet-4-6"
        )
    )

    # ── Pastas ────────────────────────────────────────
    pasta_downloads: Path = Path("downloads")
    pasta_cortes: Path = Path("cortes")
    pasta_prontos: Path = Path("output")
    pasta_fundos: Path = Path("fundos")
    pasta_musicas: Path = Path("musicas")
    pasta_audio_temp: Path = Path("temp_audio")
    pasta_logs: Path = Path("logs")

    # ── Canal ─────────────────────────────────────────
    nome_canal: str = "@BoomVibes6"
    cor_legenda: str = "white"
    tamanho_font: int = 20
    qualidade_crf: int = 22
    velocidade_enc: str = "medium"
    pitch_valor: str = "1.02"
    volume_musica: float = 0.15

    # ── Whisper ───────────────────────────────────────
    modelo_whisper: str = "base"
    idioma: str = "pt"

    # ── Durações (segundos) ───────────────────────────
    duracao_global_min: int = 30
    duracao_global_max: int = 59
    duracao_reflexao: tuple = (75, 90)
    duracao_historia: tuple = (70, 85)
    duracao_versiculo: tuple = (60, 65)

    # ── Agendador ─────────────────────────────────────
    horarios_ideais: list = field(default_factory=lambda: ["12:00", "19:00"])
    intervalo_horas: int = 3
    privacidade_padrao: str = "public"
    categoria_id: str = "22"
    daemon_intervalo_min: int = 5
    # Distribuição da fila
    proporcao_ia: int = 3
    proporcao_podcast: int = 1
    postar_tiktok: bool = True

    voz_elevenlabs_id: str = "pNInz6obpgDQGcFmaJgB"

    # ── Timeouts (segundos) ───────────────────────────
    # Timeouts diferenciados por tipo de operação para evitar travamentos
    timeout_ffprobe: int = 30  # leitura de metadados - rápido
    timeout_ffmpeg_corte: int = 120  # corte com -c copy - relativamente rápido
    timeout_ffmpeg_encode: int = 300  # recodificação completa - pode ser lento
    timeout_whisper: int = 600  # transcrição - varia muito com tamanho do vídeo

    def __post_init__(self):
        for f in [
            "pasta_downloads",
            "pasta_cortes",
            "pasta_prontos",
            "pasta_fundos",
            "pasta_musicas",
            "pasta_audio_temp",
            "pasta_logs",
        ]:
            v = getattr(self, f)
            if isinstance(v, str):
                setattr(self, f, Path(v))

    def criar_pastas(self) -> None:
        for pasta in [
            self.pasta_downloads,
            self.pasta_cortes,
            self.pasta_prontos,
            self.pasta_audio_temp,
            self.pasta_logs,
        ]:
            pasta.mkdir(parents=True, exist_ok=True)

    def validar_chaves(self) -> dict[str, list[str]]:
        """
        Retorna dict com chaves obrigatórias e opcionais.
        Uso geral (run_diario): checa tudo e decide o que bloqueia.
        """
        obrigatorios = []
        opcionais = []

        # Sempre obrigatório
        if not self.chave_anthropic:
            obrigatorios.append(
                "ANTHROPIC_API_KEY não configurada.\n"
                "  1. Copie .env.example para .env\n"
                "  2. Preencha ANTHROPIC_API_KEY=sk-ant-SuaChave\n"
                "  Crie sua chave em: https://console.anthropic.com"
            )

        # Opcionais (avisos apenas)
        if not self.chave_elevenlabs:
            opcionais.append(
                "ELEVENLABS_API_KEY não configurada (TTS premium — haverá fallback gTTS).\n"
                "  Crie sua chave em: https://elevenlabs.io/api"
            )
        if not self.telegram_token or not self.telegram_chat_id:
            opcionais.append(
                "TELEGRAM_BOT_TOKEN e/ou TELEGRAM_CHAT_ID não configurados (notificações desativadas).\n"
                "  Crie bot em @BotFather, pegue token e chat_id."
            )
        if not os.getenv("PEXELS_API_KEY"):
            opcionais.append(
                "PEXELS_API_KEY não configurada (fundos de vídeo — haverá fallback CC0).\n"
                "  Crie em: https://www.pexels.com/api/"
            )
        if not os.getenv("PIXABAY_API_KEY"):
            opcionais.append(
                "PIXABAY_API_KEY não configurada (fundos/músicas — haverá fallback CC0).\n"
                "  Crie em: https://pixabay.com/api/docs/"
            )
        if not Path("credentials.json").exists():
            opcionais.append(
                "credentials.json não encontrado (YouTube/TikTok OAuth — postagem desativada).\n"
                "  Baixe do Google Cloud Console e coloque na raiz."
            )
        if not Path("token.json").exists():
            opcionais.append(
                "token.json não encontrado (OAuth token — será gerado no primeiro uso)."
            )

        return {"obrigatorios": obrigatorios, "opcionais": opcionais}

    def validar_para_corte(self) -> list[str]:
        """Validação mínima para youtube_para_shorts.py e processar_video.py."""
        erros = []
        if not self.chave_anthropic:
            erros.append(
                "ANTHROPIC_API_KEY não configurada.\n"
                "  Crie em: https://console.anthropic.com"
            )
        return erros

    def validar_para_geracao(self) -> dict[str, list[str]]:
        """Validação para gerador_conteudo.py (IA + TTS + fundos + Telegram)."""
        obrig = []
        opc = []
        if not self.chave_anthropic:
            obrig.append("ANTHROPIC_API_KEY obrigatória para gerar roteiros.")
        if not self.chave_elevenlabs:
            opc.append("ELEVENLABS_API_KEY ausente — usará gTTS gratuito.")
        if not os.getenv("PEXELS_API_KEY"):
            opc.append("PEXELS_API_KEY ausente — fundos via fallback CC0.")
        if not os.getenv("PIXABAY_API_KEY"):
            opc.append("PIXABAY_API_KEY ausente — músicas via fallback CC0.")
        if not self.tem_telegram():
            opc.append("Telegram não configurado — notificações desativadas.")
        return {"obrigatorios": obrig, "opcionais": opc}

    def validar_para_postagem(self) -> list[str]:
        """Validação para agendador.py / servidor.py endpoints de postagem."""
        erros = []
        if not self.chave_anthropic:
            erros.append("ANTHROPIC_API_KEY obrigatória (análise de performance).")
        if not Path("credentials.json").exists():
            erros.append("credentials.json não encontrado (OAuth YouTube/TikTok).")
        # token.json pode não existir na primeira execução — não bloqueia
        return erros

    def tem_telegram(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)


# Instância global — importada pelos outros scripts
cfg = Config()
