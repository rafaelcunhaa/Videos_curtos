# Videos_curtos — guia para o Claude Code

Gera Shorts/Reels de conteúdo católico/cristão (canal @BoomVibes6) e publica no YouTube/TikTok.
Orquestração diária roda sozinha (`run_diario.py`/`agendador.py`); **não precisa de Claude Code para gerar vídeos**.

## Pipeline (gerador_conteudo.py)
roteiro (Claude API via `retry.chamar_anthropic`) → narração (ElevenLabs → edge-tts → gTTS)
→ legenda ASS (`roteiro_para_ass`) → `montar_video()`: um único comando FFmpeg (fundo + voz + música + legenda + logo, 1080x1920).
Formatos/durações em `config.py` (`duracao_*`; versículo 60–65s). Config central: `config.py` (lê `.env`).

## Outros módulos
`run_diario.py` (encadeia tudo) · `agendador.py` (YouTube) · `tiktok.py` (Playwright) · `servidor.py` + `interface.html` (dashboard FastAPI)
· `youtube_para_shorts.py`/`processar_video.py` (cortes de vídeos existentes) · `banco.py` (SQLite) · `analytics.py` · `telegram.py` · `fundos.py` (baixa fundos Pexels p/ `fundos/`).

## Fundos por IA (ComfyUI + LTX) — opt-in
- Desligado por padrão. `FUNDO_IA=1` no `.env` liga; sem clipes ou em qualquer falha, cai nos fundos de `fundos/` (comportamento antigo).
- GPU gera **pool de clipes ~4s** em lote → `fundos_ia/<tema>/*.mp4`. Cada vídeo compõe seu fundo de 60s só com FFmpeg (xfade) em CPU.
- Código: `comfyui_client.py` (API HTTP) · `fundos_ia.py` (pool + composição + CLI) · `comfy_workflows/ltx_t2v.json` (template com `{{PLACEHOLDERS}}`).
- Ponto de integração: 3 linhas em `montar_video()`.

### GPU remota (só quando autorizado — gera custo)
1. Subir pod com ComfyUI + `ltx-video-2b-v0.9.5.safetensors` (checkpoints/) e `t5xxl_fp16.safetensors` (clip/); nomes configuráveis em `COMFY_LTX_CKPT`/`COMFY_LTX_CLIP`.
2. `.env`: `COMFYUI_URL=https://<pod>:8188` (+ `COMFYUI_TOKEN` se houver proxy autenticado).
3. `python fundos_ia.py --gerar --dry-run` → confira o plano; depois `--gerar --tema ceu --n 2` (teste barato) e então o lote completo.
4. **Desligar o pod** ao terminar. Trava: máx. 48 clipes/execução; aborta após 3 falhas seguidas.

## Testes (sem GPU, sem modelos)
`python -m unittest discover -s tests -v` — servidor ComfyUI falso + clipes sintéticos; ~3 min (encodes 1080x1920 reais).

## Convenções
Código e logs em português; caminhos relativos à raiz (rodar scripts a partir dela); segredos só no `.env`.
Não alterar a ordem/semântica do pipeline sem rodar os testes. Sem commit/push sem autorização do dono.
