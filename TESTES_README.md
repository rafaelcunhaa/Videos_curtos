# Suite de Testes - Documentação Completa

## 📋 Visão Geral

Suite de testes enterprise-grade para o sistema de geração de Shorts do YouTube.

**Cobertura:**
- ✅ Testes Unitários (isolados)
- ✅ Testes de Integração (módulos múltiplos)
- ✅ Testes de Segurança (vulnerabilidades)
- ✅ Testes de Performance (benchmarks)

---

## 🚀 Quick Start

### Instalação

```bash
# Instalar dependências de teste
pip install -r requirements-test.txt

# Verificar instalação
pytest --version
```

### Executar Testes

```bash
# Todos os testes
pytest

# Com detalhes
pytest -v

# Testes específicos por marker
pytest -m "unit"           # Só unitários
pytest -m "integration"    # Só integração
pytest -m "security"       # Só segurança
pytest -m "slow"           # Só lentos (>1s)

# Testes por arquivo
pytest tests/test_banco.py
pytest tests/test_seguranca.py

# Testes por padrão
pytest -k "test_sql"       # Só testes com "sql" no nome
pytest -k "not slow"       # Excluir testes lentos
```

### Coverage (Cobertura de Código)

```bash
# Rodar com coverage
pytest --cov=. --cov-report=html --cov-report=term-missing

# Abrir relatório HTML
# Windows:
start htmlcov/index.html

# Linux/Mac:
open htmlcov/index.html
```

---

## 📁 Estrutura dos Testes

```
tests/
├── conftest.py                    # Fixtures compartilhadas
├── test_banco.py                  # Testes do banco de dados
├── test_seguranca.py              # Testes de segurança
├── test_agendador.py              # Testes de agendamento
├── test_servidor.py               # Testes da API FastAPI
├── test_gerador_conteudo.py       # Testes de geração de conteúdo
└── test_utils.py                  # Testes de utilitários
```

---

## 🧪 Fixtures Disponíveis

### Banco de Dados

```python
def test_com_banco_vazio(banco_teste):
    """Banco SQLite temporário vazio."""
    # banco_teste = caminho do arquivo .db temporário
    
def test_com_dados(banco_populado):
    """Banco com dados de teste pré-carregados."""
    # banco_populado = {"video_id": 1, "corte1_id": 1, "corte2_id": 2}
```

### Arquivos Temporários

```python
def test_com_pastas(tmp_dirs):
    """Estrutura completa de diretórios."""
    # tmp_dirs = {"downloads": Path, "cortes": Path, ...}

def test_com_video(video_fake):
    """Arquivo de vídeo fake (20KB)."""
    # video_fake = Path("test_video.mp4")

def test_com_audio(audio_fake):
    """Arquivo de áudio fake (20KB)."""
    # audio_fake = Path("test_audio.mp3")
```

### Configuração

```python
def test_com_config(config_teste):
    """Config isolada com valores fake."""
    # config_teste.chave_anthropic = "fake-key"
    # config_teste.pasta_downloads = tmp_path/downloads
```

### Mocks de API

```python
def test_com_anthropic(mock_anthropic_success):
    """Mock da API Anthropic."""
    
def test_com_subprocess(mock_subprocess_success):
    """Mock do subprocess (FFmpeg/FFprobe)."""
```

### Tempo

```python
def test_com_tempo_fixo(freeze_time):
    """Data/hora congelada em 2026-08-19 12:00:00."""
```

---

## 🎯 Markers (Tags)

Use markers para categorizar e filtrar testes:

### @pytest.mark.unit
Testes unitários isolados, rápidos.

```python
@pytest.mark.unit
def test_funcao_pura():
    assert soma(2, 2) == 4
```

### @pytest.mark.integration
Testes que tocam múltiplos módulos.

```python
@pytest.mark.integration
def test_pipeline_completo():
    video = processar_youtube(url)
    cortes = gerar_cortes(video)
    assert len(cortes) > 0
```

### @pytest.mark.security
Testes de vulnerabilidades.

```python
@pytest.mark.security
def test_sql_injection():
    # Tentar injetar SQL
    resultado = buscar_video(titulo="'; DROP TABLE videos; --")
    # Não deve executar o DROP
    assert resultado is not None
```

### @pytest.mark.slow
Testes que levam mais de 1 segundo.

```python
@pytest.mark.slow
def test_processamento_video_real():
    # Teste com vídeo real (demorado)
    pass
```

---

## 📊 Exemplos de Testes

### Teste Unitário Simples

```python
@pytest.mark.unit
def test_extrair_id_youtube():
    """Extrair ID de URL do YouTube."""
    from banco import extrair_id_youtube
    
    url = "https://youtube.com/watch?v=abc123"
    video_id = extrair_id_youtube(url)
    
    assert video_id == "abc123"
```

### Teste com Mock

```python
@pytest.mark.unit
@patch("gerador_conteudo.chamar_anthropic")
def test_gerar_roteiro_mock(mock_anthropic):
    """Gerar roteiro sem chamar API real."""
    mock_anthropic.return_value = {
        "roteiro": "Texto teste",
        "titulo": "Título",
        "hashtags": ["#teste"]
    }
    
    resultado = gerar_roteiro_completo(tema="Tech", tipo="denso")
    
    assert resultado["roteiro"] == "Texto teste"
    assert mock_anthropic.called
```

### Teste de Segurança

```python
@pytest.mark.security
def test_path_traversal_bloqueado():
    """Upload não deve permitir path traversal."""
    from servidor import app
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    
    files = {
        "arquivo": ("../../etc/passwd.mp4", b"fake", "video/mp4")
    }
    
    response = client.post("/api/upload", files=files)
    
    # Deve bloquear ou sanitizar
    assert response.status_code in [200, 400]
```

### Teste de Integração

```python
@pytest.mark.integration
def test_fluxo_completo(banco_populado):
    """Fluxo: registrar vídeo -> criar corte -> agendar -> postar."""
    video_id = banco_populado["video_id"]
    
    # 1. Buscar vídeo
    video = banco.buscar_video(video_id)
    assert video is not None
    
    # 2. Criar corte
    corte_id = banco_populado["corte1_id"]
    corte = banco.buscar_corte(corte_id)
    assert corte["status"] == "pronto"
    
    # 3. Agendar
    banco.atualizar_status_corte(corte_id, "agendado")
    assert banco.buscar_corte(corte_id)["status"] == "agendado"
```

---

## 🛡️ Testes de Segurança

A suite valida as correções documentadas em `CORRECOES_APLICADAS.md`:

### Vulnerabilidades Testadas

1. **Path Traversal** - `test_seguranca.py::TestPathTraversal`
2. **SQL Injection** - `test_seguranca.py::TestSQLInjection`
3. **Rate Limiting** - `test_seguranca.py::TestRateLimiting`
4. **Validação de URL** - `test_seguranca.py::TestValidacaoURL`
5. **Resource Leaks** - `test_seguranca.py::TestResourceLeaks`
6. **Race Conditions** - `test_seguranca.py::TestRaceConditions`
7. **Input Validation** - `test_seguranca.py::TestInputValidation`
8. **Timeouts** - `test_seguranca.py::TestTimeouts`

### Executar Só Testes de Segurança

```bash
pytest -m security -v
```

---

## 🔧 Configuração Avançada

### pytest.ini

Configuração global em `pytest.ini`:

```ini
[pytest]
markers =
    unit: Testes unitários
    integration: Testes de integração
    security: Testes de segurança
    slow: Testes lentos

addopts = -v -ra
```

### Paralelização

Rodar testes em paralelo (mais rápido):

```bash
# Instalar
pip install pytest-xdist

# Rodar com 4 workers
pytest -n 4

# Auto-detectar número de CPUs
pytest -n auto
```

### Timeout

Evitar testes travados:

```bash
# Instalar
pip install pytest-timeout

# Timeout global de 60s
pytest --timeout=60

# Timeout por teste
@pytest.mark.timeout(10)
def test_rapido():
    pass
```

---

## 📈 CI/CD Integration

### GitHub Actions

Configurado em `.github/workflows/tests.yml`:

- ✅ Roda automaticamente em push/PR
- ✅ Testa em Python 3.10, 3.11, 3.12
- ✅ Testa em Ubuntu e Windows
- ✅ Gera relatórios de coverage
- ✅ Executa security checks (Bandit, Safety)
- ✅ Executa linters (Black, isort, flake8, mypy)

### Rodar Localmente Como CI

```bash
# Todos os checks
pytest -v
black --check .
isort --check-only .
flake8 .
mypy . --ignore-missing-imports
bandit -r .
safety check
```

---

## 📋 Checklist de Qualidade

Antes de fazer commit/PR:

- [ ] Todos os testes passam: `pytest`
- [ ] Coverage adequado: `pytest --cov` (>70%)
- [ ] Testes de segurança passam: `pytest -m security`
- [ ] Código formatado: `black .`
- [ ] Imports ordenados: `isort .`
- [ ] Sem erros de lint: `flake8 .`
- [ ] Type hints válidos: `mypy .`
- [ ] Sem vulnerabilidades: `safety check`

---

## 🐛 Troubleshooting

### Testes Falhando

```bash
# Mostrar output completo
pytest -v -s

# Parar no primeiro erro
pytest -x

# Mostrar traceback completo
pytest --tb=long
```

### Import Errors

```bash
# Adicionar path do projeto
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Ou no pytest
pytest --import-mode=importlib
```

### Banco de Dados Travado

```bash
# Limpar arquivos .db temporários
rm -rf /tmp/tmp*.db
```

---

## 📚 Recursos

- [Pytest Docs](https://docs.pytest.org/)
- [Coverage.py](https://coverage.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Python Testing Best Practices](https://realpython.com/pytest-python-testing/)

---

## ✅ Status

**Suite Completa:** ✅  
**Coverage Target:** 70%+  
**CI/CD:** ✅ GitHub Actions  
**Security Tests:** ✅ Todas as vulnerabilidades cobertas

---

**Última Atualização:** 19/08/2026  
**Autor:** Sistema de Testes Enterprise
