# Revisão de Segurança e Qualidade do Código

**Data:** 19/08/2026  
**Objetivo:** Identificar vulnerabilidades, bugs potenciais e melhorias para código nível sênior

---

## 🔴 CRÍTICO - Vulnerabilidades de Segurança

### 1. **Command Injection em `agendador.py` (linha 543-545)**
```python
def limpar_video_apos_postagem(caminho_video: str) -> None:
    # Função referenciada mas NÃO IMPLEMENTADA no código
    # Chamada na linha 545 mas a função não existe
```
**Problema:** Função chamada mas não definida - vai causar `NameError` em runtime.  
**Severidade:** CRÍTICA - quebra funcionalidade de limpeza pós-postagem.  
**Fix:** Implementar a função ou usar `excluir_video_local()` que já existe.

---

### 2. **Path Traversal em `servidor.py` (linha 60-72)**
```python
def secure_path(*parts: str) -> Path:
    """Constrói um caminho seguro dentro de BASE_DIR."""
    base = BASE_DIR.resolve()
    caminho = base
    for p in parts:
        nome = Path(str(p)).name  # descarta diretórios e '..'
        caminho = caminho / nome
    if not str(caminho.resolve()).startswith(str(base)):
        raise ValueError(f"Caminho fora do diretório permitido: {caminho}")
    return caminho
```
**Problema PARCIAL:** A função existe e valida, MAS não é usada consistentemente em todos os endpoints.  
- ✅ Usado em `/api/output/download/{nome}` (linha 752)
- ❌ NÃO usado em outros lugares que manipulam arquivos

**Exemplo de endpoint vulnerável:**
```python
# servidor.py linha 391-394
tmp_path = BASE_DIR / "downloads" / f"upload_{datetime.now().strftime('%H%M%S')}{ext}"
# Se 'arquivo.filename' contiver '../../../malicious.mp4', pode escapar do diretório
```
**Severidade:** ALTA  
**Fix:** Validar `arquivo.filename` usando `secure_path()` ou `Path().name`.

---

### 3. **SQL Injection MITIGADO mas Comentário Incorreto em `banco.py`**
```python
# banco.py linhas 259-269
def listar_cortes(video_id: Optional[int] = None, status: Optional[str] = None):
    # nosec B608 — comentário diz que é seguro, e ESTÁ CORRETO
    # Query usa placeholders '?' e parâmetros são passados como lista separada
    query = f"""SELECT c.*, v.titulo AS titulo_video, v.youtube_id
                FROM cortes c JOIN videos v ON v.id = c.video_id
                WHERE {' AND '.join(condicoes)}
                ORDER BY c.criado_em DESC"""
    rows = conn.execute(query, params).fetchall()
```
**Status:** ✅ SEGURO - apesar do f-string, os valores vão em `params` parametrizados.  
**Observação:** O comentário `# nosec B608` está correto. Não é vulnerabilidade.

---

### 4. **Falta de Rate Limiting no Servidor FastAPI**
**Arquivo:** `servidor.py`  
**Problema:** Nenhum rate limiting nos endpoints da API.  
**Risco:** Um usuário pode fazer milhares de requisições e:
- Gastar toda a cota da API Anthropic
- Sobrecarregar o servidor
- Criar DoS local

**Severidade:** MÉDIA  
**Fix:** Adicionar middleware de rate limiting:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/gerar")
@limiter.limit("5/minute")  # máximo 5 gerações por minuto
async def gerar_conteudo(...):
```

---

### 5. **Host do Servidor Exposto Localmente mas Comentário Inadequado**
```python
# servidor.py linha 802-804
uvicorn.run(
    app,
    host="127.0.0.1",  # uso local apenas
    port=8000,
)
```
**Status:** ✅ CORRETO - usa localhost apenas  
**Problema MENOR:** O comentário menciona "não expor a outros dispositivos da rede" mas não explica o RISCO (controla postagem e gasto de API sem autenticação).

---

## 🟡 ALTO - Bugs e Problemas de Lógica

### 6. **Race Condition em Data de Agendamento**
**Arquivo:** `agendador.py` linhas 343-357  
```python
for ag in agendados:
    if ag.get("agendado_para"):
        try:
            horarios_ocupados.append(
                datetime.strptime(ag["agendado_para"], "%Y-%m-%d %H:%M:%S")
            )
        except Exception:
            # Se conversão falhar, a data malformada é SILENCIOSAMENTE ignorada
            # Isso permite dois vídeos agendados no mesmo horário
            logger.warning("Corte %s tem agendado_para malformado: %r", ...)
```
**Problema:** Data malformada no banco é ignorada, causando conflitos de horário.  
**Severidade:** ALTA - pode causar postagens duplicadas no mesmo horário.  
**Fix:** Validar formato da data ANTES de gravar no banco (já existe em `agendar_corte` linha 294-297, mas não é aplicado universalmente).

**Ocorrências:**
- `agendador.py:350` (agendar_corte_automatico)
- `agendador.py:438` (agendar_lote)
- `agendador.py:640-652` (listar_fila - só exibição, ok)

---

### 7. **Timeout Hardcoded e Muito Alto**
**Problema:** Todos os comandos `subprocess.run()` têm `timeout=300` (5 minutos).  

**Arquivos afetados:**
- `banco.py:487` (ffprobe)
- `youtube_para_shorts.py:242` (ffmpeg corte)
- `youtube_para_shorts.py:334` (ffmpeg processar)
- `gerador_conteudo.py:410` (ffprobe)
- `gerador_conteudo.py:580` (ffmpeg montar)
- `processar_video.py:115` (ffprobe)
- `processar_video.py:254` (ffmpeg corte)
- `processar_video.py:357` (ffmpeg processar)

**Problema:** 
1. 5 minutos é excessivo para operações que geralmente levam segundos
2. Timeout muito alto pode fazer o sistema travar por muito tempo em caso de erro
3. Operações diferentes precisam de timeouts diferentes

**Severidade:** MÉDIA  
**Fix:** Usar timeouts adequados:
```python
TIMEOUTS = {
    "ffprobe": 30,      # leitura de metadados - rápido
    "ffmpeg_corte": 120,  # corte simples com -c copy
    "ffmpeg_encode": 300, # recodificação completa - pode ser lento
    "whisper": 600,     # transcrição - pode ser bem lento
}
```

---

### 8. **Resource Leak Potencial - Arquivo Audio Temporário**
**Arquivo:** `gerador_conteudo.py` linhas 641-653  
```python
audio_path = Path(PASTA_AUDIO_TEMP) / f"audio_{formato}_{ts}.mp3"
ok = gerar_audio(dados["roteiro"], audio_path)
if not ok:
    log("Falha ao gerar áudio.", "ERRO")
    return None, None  # LEAK: audio_path não é deletado

video_out, txt_out = montar_video(dados, audio_path, PASTA_PRONTOS)

# Limpar áudio temp
if audio_path.exists():
    audio_path.unlink()  # Só deleta se chegou aqui
```
**Problema:** Se `gerar_audio()` retornar `False` mas criar o arquivo parcialmente, o arquivo não é deletado.  
**Severidade:** BAIXA - polui pasta temporária ao longo do tempo.  
**Fix:** Usar `try/finally` ou context manager.

---

### 9. **Retry Logic Tem Código Morto**
**Arquivo:** `retry.py` linhas 126-129  
```python
def _call():
    if not _erro_temporario_anthropic(Exception()):  # sempre tenta
        pass  # não faz nada
    return func(*args, **kwargs)
```
**Problema:** A função `_call()` é definida mas NUNCA é chamada. O código real está nas linhas 132-151 (implementação manual do retry).  
**Severidade:** BAIXA - código morto, não afeta funcionalidade.  
**Fix:** Remover função `_call()` não utilizada.

---

### 10. **Divisão por Zero Não Protegida**
**Arquivo:** `gerador_conteudo.py` linha 443  
```python
seg_por_palavra = duracao_audio / max(palavras_total, 1)
```
**Status:** ✅ PROTEGIDO com `max(palavras_total, 1)`  

**Arquivo:** `gerador_conteudo.py` linha 414  
```python
def obter_duracao_audio(caminho: Path) -> float:
    try:
        return float(json.loads(res.stdout)["format"]["duration"])
    except Exception:
        return 0.0  # retorna 0 em caso de erro
```
**Problema POTENCIAL:** Se `obter_duracao_audio()` retornar `0.0`, isso pode causar problemas em:
```python
# linha 443 - OK, protegido
seg_por_palavra = duracao_audio / max(palavras_total, 1)

# linha 499 - NÃO PROTEGIDO contra duracao == 0
if duracao < 1:
    log("Áudio inválido ou muito curto.", "ERRO")
    return None, None
```
**Status:** ✅ PROTEGIDO indiretamente - se duração < 1, retorna erro.

---

## 🟢 MÉDIO - Melhorias de Código Sênior

### 11. **Logging Inconsistente**
**Problema:** Mistura de `print()` e `logger.info()` em todo o código.

**Exemplos:**
```python
# youtube_para_shorts.py linha 70
def log(msg: str, nivel: str = "INFO") -> None:
    print(f"[{hora}] {p.get(nivel,'·')} {msg}")  # print direto

# banco.py linha 117
logger.info("Banco inicializado: %s", BANCO_ARQUIVO)  # logger correto
```
**Severidade:** BAIXA  
**Fix:** Padronizar usando apenas `logger` com níveis apropriados.

---

### 12. **Magic Numbers Espalhados**
**Problema:** Constantes hardcoded sem explicação.

**Exemplos:**
```python
# servidor.py linha 74
MAX_LOGS_BUFFER = 500  # por que 500?

# agendador.py linha 216
chunksize=10 * 1024 * 1024  # 10MB - deveria estar em constante

# banco.py linha 44
timeout=10  # segundos - deveria ser BANCO_TIMEOUT

# gerador_conteudo.py linha 82
VIDEOS_POR_DIA = {"reflexao": 4, "historia": 4, "versiculo": 2}
# totais não batem com documentação que fala em "2 longos + 1 médio"
```

---

### 13. **Falta de Type Hints Completos**
**Problema:** Algumas funções não têm type hints ou têm incompletos.

**Exemplos:**
```python
# banco.py linha 402
def parse_txt(txt_path: Path) -> dict:  # dict de quê?
    # deveria ser -> dict[str, Any] ou criar TypedDict

# agendador.py linha 307
def proximos_horarios(quantidade: int = 10) -> list:  # list de quê?
    # deveria ser -> list[datetime]
```

---

### 14. **Validação de Entrada Insuficiente**

**servidor.py linha 339:**
```python
if not req.url.startswith("http"):
    raise HTTPException(400, "URL inválida")
```
**Problema:** Validação muito fraca. Aceita `http://` ou `https://` mas não valida se é uma URL real do YouTube.  
**Risco:** Permite URLs maliciosas que podem causar problemas no `yt-dlp`.

**Fix:**
```python
import re
YOUTUBE_REGEX = r'^https?://(www\.)?(youtube\.com|youtu\.be)/.+'
if not re.match(YOUTUBE_REGEX, req.url):
    raise HTTPException(400, "URL deve ser do YouTube")
```

---

### 15. **Tratamento de Exceção Genérico**
**Problema:** Uso excessivo de `except Exception:` que captura tudo.

**Exemplos:**
```python
# telegram.py linha 78
try:
    from config import cfg
    if cfg.telegram_token and cfg.telegram_chat_id:
        # ...
except Exception:  # captura TUDO, até KeyboardInterrupt
    pass
```
**Severidade:** BAIXA  
**Fix:** Capturar exceções específicas:
```python
except (ImportError, AttributeError):
    pass
```

---

### 16. **Constantes Duplicadas**
**Problema:** Mesmas constantes definidas em múltiplos arquivos.

**Exemplo:**
```python
# youtube_para_shorts.py linha 65
CORES_ASS = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00"}

# processar_video.py linha 75
CORES_ASS = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00"}

# gerador_conteudo.py linha 85
CORES_ASS = {"white": "&H00FFFFFF", "yellow": "&H0000FFFF", "cyan": "&H00FFFF00"}
```
**Fix:** Mover para `config.py` ou criar `constantes.py`.

---

### 17. **Conversão de Taxa de Câmbio Hardcoded**
**Problema:** Conversão BRL hardcoded em vários lugares com valores diferentes!

```python
# banco.py linha 634
custo_brl = s["custo_total_usd"] * 5.6

# telegram.py linha 168
custo_brl = custo_usd * 5.6

# servidor.py linha 160
custo_brl = s.get("custo_total_usd", 0) * 5.6
```
**Problema:** Taxa de câmbio desatualizada e hardcoded.  
**Fix:** 
1. Criar constante `TAXA_CAMBIO_BRL = 5.6` em `config.py`
2. Ou melhor: buscar taxa real de uma API (opcional)

---

## 🔵 BAIXO - Melhorias de Qualidade

### 18. **Docstrings Incompletas**
Muitas funções não têm docstrings ou têm docstrings vagas.

### 19. **Testes Unitários Ausentes**
Não há pasta `tests/` nem testes automatizados.

### 20. **Arquivos `.gitignore` Muito Amplo**
```python
# .gitignore linha 47
*.json
```
**Problema:** Bloqueia TODOS os .json, incluindo `package.json` se adicionar frontend.  
**Fix:** Ser mais específico:
```
credentials.json
token.json
token_tiktok.json
*_session.json
```

---

## ✅ Pontos Positivos (Código Bem Feito)

1. ✅ **Context Manager para Banco** (`banco.py:42-55`) - garante fechamento de conexões
2. ✅ **Foreign Keys Habilitadas** (`banco.py:47`) - integridade referencial
3. ✅ **WAL Mode no SQLite** (`banco.py:46`) - melhor concorrência
4. ✅ **Retry com Backoff Exponencial** (`retry.py`) - resiliente a falhas de API
5. ✅ **Validação de Status no Banco** (`banco.py:278-280`) - previne valores inválidos
6. ✅ **Path Traversal Mitigado** (`servidor.py:60-72`) - função existe
7. ✅ **SQL Parametrizado** - todas as queries usam placeholders
8. ✅ **Sanitização de Nomes de Arquivo** (`youtube_para_shorts.py:233-236`)
9. ✅ **Remoção de Metadados** - FFmpeg com `-map_metadata -1`
10. ✅ **Notificações Resilientes** - falha silenciosa se Telegram não configurado

---

## 📊 Resumo Executivo

| Categoria | Quantidade | Exemplos |
|-----------|------------|----------|
| 🔴 Crítico | 2 | Função não implementada, Path traversal parcial |
| 🟡 Alto | 5 | Race condition, Timeouts altos, Resource leak |
| 🟢 Médio | 7 | Logging, Magic numbers, Type hints, Validação |
| 🔵 Baixo | 3 | Docstrings, Testes, .gitignore |

---

## 🎯 Prioridades de Fix

### Sprint 1 (Urgente - 1 dia)
1. Implementar `limpar_video_apos_postagem()` em `agendador.py`
2. Adicionar validação de `filename` com `secure_path()` em uploads
3. Fix race condition de datas malformadas em agendamento

### Sprint 2 (Importante - 3 dias)
4. Adicionar rate limiting no FastAPI
5. Ajustar timeouts por tipo de operação
6. Corrigir resource leak de áudio temporário
7. Remover código morto em `retry.py`

### Sprint 3 (Melhoria - 1 semana)
8. Padronizar logging
9. Extrair constantes duplicadas
10. Adicionar type hints completos
11. Melhorar validação de entrada

### Sprint 4 (Opcional - backlog)
12. Adicionar testes unitários
13. Melhorar docstrings
14. Refatorar taxa de câmbio
