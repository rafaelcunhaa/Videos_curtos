# Quality Gate — ETAPA 4

Camada isolada que **valida, classifica e reporta** o vídeo final antes da publicação. Não corrige, recodifica, move legendas ou gera assets.

## Ativação

Desativado por padrão para preservar o comportamento existente:

```env
QUALITY_GATE_ENABLED=false
QUALITY_GATE_MODE=normal
QUALITY_EXPECT_AUDIO=true
QUALITY_EXPECT_CAPTIONS=false
QUALITY_EXPECT_THUMBNAIL=false
QUALITY_MIN_DURATION_S=10
QUALITY_MAX_DURATION_S=120
QUALITY_DURATION_TOLERANCE_S=1.5
QUALITY_ALLOWED_RESOLUTIONS=1080x1920,720x1280,1080x1080
```

A integração opt-in é `pipeline.quality_gate.run_quality_gate_for_job(job_manager, video_path, ...)`. Ela registra o resultado usando o `JobManager` da ETAPA 2; não chama o publicador.

## Resultado

- `APPROVED`: checks críticos passaram.
- `WARNING`: apenas warnings no modo `normal`; pode prosseguir com alerta.
- `BLOCKED`: check `CRITICAL` ou `ERROR` falhou; não deve ser agendado/publicado.

Cada check retorna `name`, `status` (`PASS`, `WARN`, `FAIL`, `SKIPPED`), `severity`, `message` e, quando útil, `metadata`. `GateReport` produz texto legível e JSON.

## Checks

Arquivo, integridade/container/streams via `ffprobe`, resolução/proporção, duração com tolerância, áudio esperado, legendas opcionais, manifest/assets, thumbnail opcional e regras determinísticas de título/descrição/CTA. O `SceneValidator` do módulo Gemini continua sendo a validação de cena própria; não é duplicado.

O cache é indexado por hash parcial do arquivo e o resultado nunca é usado para arquivo inexistente/vazio. A política fica centralizada em `pipeline/quality_gate/policy.py`.

## Strict

`QUALITY_GATE_MODE=strict` transforma warnings de checks em bloqueio. Use apenas quando a configuração exigir uma barreira mais rígida.

## Integração com publicação

Nenhum arquivo de publicação foi alterado nesta etapa. O chamador deve executar o gate antes de agendar e impedir o avanço quando `status == BLOCKED`. Uma integração direta com `agendador.py` será uma mudança separada, após revisão explícita do ponto de publicação.
