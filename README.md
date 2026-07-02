# 📁 Sistema de Shorts — Guia Completo

Coloque todos os arquivos na **mesma pasta**. É só isso.

```
📁 minha-pasta/
├── banco.py                ← banco de dados (usado por todos)
├── youtube_para_shorts.py  ← baixa do YouTube + corta + processa
├── processar_video.py      ← vídeo local + corta + processa
├── agendador.py            ← agenda e posta automaticamente
└── COMO_USAR.md            ← este guia
```

---

## 🚀 Instalação (uma vez só)

```bash
pip install yt-dlp openai-whisper anthropic google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client schedule
```
FFmpeg: https://ffmpeg.org/download.html

---

## ⚙️ Configurar sua chave Anthropic

```bash
# Mac/Linux
export ANTHROPIC_API_KEY=sk-ant-SuaChaveAqui

# Windows
set ANTHROPIC_API_KEY=sk-ant-SuaChaveAqui
```
Crie sua chave em: https://console.anthropic.com

---

## 📺 Fluxo 1 — Vídeo do YouTube

```bash
python youtube_para_shorts.py --url https://youtu.be/XXXXXXXXX
```
Baixa → transcreve → IA corta → processa → salva em `output/`

---

## 📁 Fluxo 2 — Vídeo que você já tem no computador

```bash
python processar_video.py --arquivo meu_video.mp4
```
Transcreve → IA corta → processa para TikTok + Shorts → salva em `output/`

```bash
# Processar todos os vídeos de uma pasta de uma vez
python processar_video.py --pasta ./meus_videos
```

---

## 📅 Fluxo 3 — Agendar e postar automaticamente

```bash
# 1. Autenticar com YouTube (uma vez só)
python agendador.py --auth

# 2. Agendar todos os cortes prontos
python agendador.py --agendar-lote

# 3. Ver a fila
python agendador.py --listar

# 4. Deixar postando sozinho
python agendador.py --daemon
```

---

## 📋 Referência rápida de todos os comandos

### youtube_para_shorts.py
```bash
--url URL              # processar vídeo do YouTube
--url URL --forcar     # reprocessar mesmo se já estiver no banco
--modelo small         # usar modelo Whisper mais preciso
```

### processar_video.py
```bash
--arquivo video.mp4    # processar vídeo local
--pasta ./videos       # processar todos da pasta
--arquivo v.mp4 --forcar  # reprocessar
--modelo small         # modelo Whisper mais preciso
```

### banco.py
```bash
--listar               # todos os vídeos processados
--listar-prontos       # cortes prontos para postar
--listar-cortes ID     # cortes de um vídeo específico
--stats                # custo total e resumo geral
--resetar URL_OU_ID    # permite reprocessar um vídeo
```

### agendador.py
```bash
--auth                          # autenticar com YouTube
--agendar-lote                  # agenda tudo automaticamente
--agendar ID --data "AAAA-MM-DD HH:MM"  # data específica
--listar                        # fila de agendamentos
--postar-agora ID               # posta imediatamente
--daemon                        # roda em loop postando
```

---

## ⚙️ O que editar em cada arquivo

### youtube_para_shorts.py e processar_video.py
```python
NOME_CANAL      = "@SeuCanal"   # seu @ do YouTube/TikTok
COR_LEGENDA     = "white"       # white | yellow | cyan
MODELO_WHISPER  = "base"        # tiny | base | small | medium | large
IDIOMA          = "pt"          # pt | en | auto
```

### agendador.py
```python
HORARIOS_IDEAIS    = ["07:00","12:00","18:00","21:00"]
INTERVALO_HORAS    = 3          # mínimo entre posts
PRIVACIDADE_PADRAO = "public"   # public | private | unlisted
```

---

## 📊 Modelos Whisper

| Modelo | Velocidade | Precisão |
|--------|-----------|----------|
| tiny   | Muito rápido | Baixa |
| base   | Rápido | Boa ✓ |
| small  | Médio | Ótima |
| medium | Lento | Excelente |
| large  | Muito lento | Máxima |

---

## 📁 Pastas geradas automaticamente

```
📁 minha-pasta/
├── downloads/          ← vídeos baixados do YouTube
├── cortes/             ← cortes brutos (intermediário)
├── output/             ← ✅ vídeos prontos + .txt com título/descrição
└── banco_shorts.db     ← banco de dados SQLite
```

---

## 🎬 gerador_conteudo.py — Vídeos 100% originais

Gera vídeos religiosos originais com IA — sem precisar de nenhum vídeo externo.

### Configuração extra
```bash
# Voz gratuita (já funciona sem nada)
pip install gtts

# Voz profissional ElevenLabs (opcional — R$28/mês)
export ELEVENLABS_API_KEY=sua_chave_aqui
```

### Comandos
```bash
# Gerar os 3 vídeos do dia (padrão)
python gerador_conteudo.py

# Gerar quantidade específica
python gerador_conteudo.py --quantidade 4

# Só vídeos longos (>60s)
python gerador_conteudo.py --longo

# Formato específico
python gerador_conteudo.py --formato reflexao
python gerador_conteudo.py --formato historia
python gerador_conteudo.py --formato versiculo

# Com tema específico
python gerador_conteudo.py --formato reflexao --tema "ansiedade e fé"
python gerador_conteudo.py --formato historia --tema "Davi e Golias"
python gerador_conteudo.py --formato versiculo --tema "Salmos 91"
```

### Distribuição de duração (otimizada para monetização)
| Formato | Duração | RPM |
|---|---|---|
| Reflexão do dia | 75–90s | Máximo |
| História bíblica/santo | 70–85s | Máximo |
| Versículo do dia | 60–65s | Base monetização |

### Pastas que você precisa criar (opcional mas recomendado)
```
📁 fundos/    ← vídeos de fundo (natureza, céu, água, nuvens)
              Baixe de: pexels.com/videos — gratuito e sem copyright
📁 musicas/   ← músicas instrumentais de fundo
              Baixe de: pixabay.com/music — gratuito e sem copyright
```
Sem essas pastas, o vídeo fica com fundo preto — funciona, mas fica menos bonito.

### Rotina diária completa (4 vídeos/dia)
```bash
# Gerar 3 originais
python gerador_conteudo.py --quantidade 3

# Processar 1 corte de podcast
python youtube_para_shorts.py --url https://youtu.be/XXXXXXXXX

# Agendar tudo
python agendador.py --agendar-lote

# Ver fila
python agendador.py --listar
```