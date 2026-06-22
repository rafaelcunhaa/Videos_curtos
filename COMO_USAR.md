# 📁 Sistema de Shorts — Todos os Arquivos

Coloque todos os arquivos na **mesma pasta**. É só isso.

```
📁 minha-pasta/
├── banco.py                ← banco de dados (usado pelos outros)
├── youtube_para_shorts.py  ← pipeline principal (baixar + cortar + processar)
├── agendador.py            ← agendar e postar no YouTube automaticamente
└── processar_video.py      ← processar vídeos avulsos que você já tem
```

---

## 🚀 Fluxo completo do zero

### 1. Instalar dependências (uma vez só)
```bash
pip install yt-dlp openai-whisper anthropic google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client schedule
```
Instalar FFmpeg: https://ffmpeg.org/download.html

### 2. Configurar chaves
```bash
# Chave Anthropic (https://console.anthropic.com)
export ANTHROPIC_API_KEY=sk-ant-SuaChaveAqui
```

### 3. Processar um vídeo do YouTube
```bash
python youtube_para_shorts.py --url https://youtu.be/XXXXXXXXX
```
→ Gera os Shorts prontos em `output/`

### 4. Ver os cortes no banco
```bash
python banco.py --listar-prontos
```

### 5. Agendar postagem automática
```bash
# Configurar conta YouTube (uma vez só)
python agendador.py --auth

# Agendar todos os cortes prontos
python agendador.py --agendar-lote

# Ver a fila
python agendador.py --listar

# Deixar postando sozinho
python agendador.py --daemon
```

---

## 📋 Referência rápida de comandos

| Arquivo | Comando | O que faz |
|---|---|---|
| `youtube_para_shorts.py` | `--url URL` | Baixa, corta e processa |
| `youtube_para_shorts.py` | `--url URL --forcar` | Reprocessa vídeo já no banco |
| `banco.py` | `--listar` | Lista vídeos processados |
| `banco.py` | `--listar-prontos` | Lista cortes prontos |
| `banco.py` | `--stats` | Custo total de API |
| `agendador.py` | `--auth` | Autentica com YouTube |
| `agendador.py` | `--agendar-lote` | Agenda tudo automaticamente |
| `agendador.py` | `--listar` | Mostra fila de postagem |
| `agendador.py` | `--postar-agora ID` | Posta imediatamente |
| `agendador.py` | `--daemon` | Roda em loop postando |
| `processar_video.py` | *(sem args)* | Processa pasta `input/` |

---

## ⚙️ O que editar em cada arquivo

### `youtube_para_shorts.py` — linha ~20
```python
CHAVE_ANTHROPIC = "sk-ant-SuaChave"  # sua chave
NOME_CANAL      = "@SeuCanal"        # seu @ do YouTube
MODELO_WHISPER  = "base"             # tiny/base/small/medium/large
```

### `agendador.py` — linha ~40
```python
HORARIOS_IDEAIS  = ["07:00","12:00","18:00","21:00"]  # quando postar
INTERVALO_HORAS  = 3    # mínimo entre posts
PRIVACIDADE_PADRAO = "public"  # public/private/unlisted
```

### `processar_video.py` — linha ~50
```python
NOME_CANAL = "@SeuCanal"   # seu @ do YouTube
COR_LEGENDA = "white"      # cor das legendas
```