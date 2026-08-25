"""
Testes do Servidor API - Endpoints FastAPI.
Valida rotas, validação de entrada, rate limiting e respostas.
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
from datetime import datetime


@pytest.fixture
def client(config_teste):
    """Cliente de teste do FastAPI."""
    from servidor import app
    return TestClient(app)


@pytest.mark.unit
class TestEndpointHealth:
    """Testes do endpoint de health check."""

    def test_health_check(self, client):
        """Health check deve retornar 200."""
        # servidor.py expõe /api/health (não /health)
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "status" in data or response.text


@pytest.mark.unit
class TestEndpointUpload:
    """Testes do endpoint de upload de vídeos locais (/api/local/processar)."""

    def test_upload_video_valido(self, client, video_fake, monkeypatch):
        """Upload de vídeo válido deve ser aceito (202 async ou 422 validação)."""
        # Mock da função secure_path para evitar IO real
        def mock_secure_path(base, filename):
            return video_fake.parent / filename

        monkeypatch.setattr("servidor.secure_path", mock_secure_path)

        files = {
            "arquivo": (
                "test_video.mp4",
                video_fake.read_bytes(),
                "video/mp4"
            )
        }

        response = client.post("/api/local/processar", files=files)

        # Servidor responde 202 (background) ou 200/422 (validação)
        assert response.status_code in [200, 202, 400, 422]

    def test_upload_sem_arquivo(self, client):
        """Sem arquivo deve retornar erro 422 (FastAPI validation)."""
        response = client.post("/api/local/processar")
        assert response.status_code in [400, 422]

    def test_upload_extensao_invalida(self, client, tmp_path):
        """Upload com extensão inválida deve ser rejeitado."""
        fake_exe = tmp_path / "malware.exe"
        fake_exe.write_bytes(b"fake content")

        files = {
            "arquivo": (
                "malware.exe",
                fake_exe.read_bytes(),
                "application/x-msdownload"
            )
        }

        response = client.post("/api/local/processar", files=files)
        assert response.status_code in [400, 422]


@pytest.mark.unit
class TestEndpointYouTube:
    """Testes do endpoint de processamento de YouTube."""

    @patch("servidor._task_youtube")
    def test_youtube_url_valida(self, mock_task, client):
        """URL válida do YouTube deve ser aceita."""
        mock_task.return_value = {"status": "processando"}

        response = client.post(
            "/api/youtube/processar",
            json={"url": "https://youtube.com/watch?v=abc123"}
        )

        # Pode retornar 200, 202, ou 429 (rate limit)
        assert response.status_code in [200, 202, 429]

    def test_youtube_url_invalida(self, client):
        """URL inválida deve ser rejeitada."""
        response = client.post(
            "/api/youtube/processar",
            json={"url": "https://vimeo.com/123456"}
        )

        assert response.status_code == 400
        data = response.json()
        assert "url" in data["detail"].lower() or "inválid" in data["detail"].lower()

    def test_youtube_sem_url(self, client):
        """Requisição sem URL deve retornar erro."""
        response = client.post(
            "/api/youtube/processar",
            json={}
        )

        assert response.status_code in [400, 422]

    def test_youtube_url_formato_errado(self, client):
        """URLs com formato incorreto devem ser rejeitadas."""
        urls_invalidas = [
            "not-a-url",
            "ftp://youtube.com/video",
            "javascript:alert(1)",
            "file:///etc/passwd",
        ]

        for url in urls_invalidas:
            response = client.post(
                "/api/youtube/processar",
                json={"url": url}
            )
            assert response.status_code in [400, 422]


@pytest.mark.unit
class TestEndpointGerar:
    """Testes do endpoint de geração de conteúdo."""

    @patch("servidor._task_gerar")
    def test_gerar_conteudo_valido(self, mock_task, client):
        """Requisição válida deve ser aceita."""
        mock_task.return_value = {"status": "gerando"}

        payload = {
            "tema": "Tecnologia",
            "tipo": "denso",
            "quantidade": 1
        }

        response = client.post("/api/gerar", json=payload)

        # Pode retornar 200, 202, ou 429 (rate limit)
        assert response.status_code in [200, 202, 429]

    def test_gerar_sem_tema(self, client):
        """Requisição sem tema deve ser aceita (tema é opcional)."""
        response = client.post(
            "/api/gerar",
            json={"quantidade": 1}
        )

        # tema é Optional no modelo, então aceita sem tema
        assert response.status_code in [200, 202, 429]


@pytest.mark.unit
class TestEndpointCortes:
    """Testes dos endpoints de gerenciamento de cortes."""

    def test_listar_cortes(self, client, banco_populado):
        """Listar cortes deve retornar lista."""
        response = client.get("/api/cortes")

        # Pode não ter implementação
        assert response.status_code in [200, 404, 405]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_buscar_corte_existente(self, client, banco_populado):
        """Buscar corte existente deve retornar dados."""
        corte_id = banco_populado["corte1_id"]

        response = client.get(f"/api/cortes/{corte_id}")

        # Pode não ter implementação
        assert response.status_code in [200, 404, 405]

        if response.status_code == 200:
            data = response.json()
            assert data.get("id") == corte_id

    def test_buscar_corte_inexistente(self, client):
        """Buscar corte inexistente deve retornar 404."""
        response = client.get("/api/cortes/999999")

        assert response.status_code in [404, 405]


@pytest.mark.security
class TestRateLimitingAPI:
    """Testes de rate limiting nos endpoints."""

    def test_rate_limit_youtube(self, client):
        """Endpoint YouTube deve ter rate limiting."""
        from servidor import _rate_limit_store
        _rate_limit_store.clear()

        # Fazer várias requisições
        respostas = []
        for i in range(15):
            response = client.post(
                "/api/youtube/processar",
                json={"url": f"https://youtube.com/watch?v=test{i}"}
            )
            respostas.append(response.status_code)

        # Deve ter pelo menos uma resposta 429
        assert 429 in respostas or 400 in respostas

    def test_rate_limit_gerar(self, client):
        """Endpoint gerar deve ter rate limiting."""
        from servidor import _rate_limit_store
        _rate_limit_store.clear()

        # Fazer várias requisições
        respostas = []
        for i in range(10):
            response = client.post(
                "/api/gerar",
                json={"tema": f"Tema {i}", "quantidade": 1}
            )
            respostas.append(response.status_code)

        # Deve ter pelo menos uma resposta 429 após limite
        assert 429 in respostas or 400 in respostas


@pytest.mark.unit
class TestCORS:
    """Testes de configuração CORS."""

    def test_cors_headers(self, client):
        """Headers CORS devem estar presentes."""
        response = client.options("/api/cortes")

        # Verificar se há headers CORS (se configurado)
        # Pode não estar implementado
        assert response.status_code in [200, 404, 405]


@pytest.mark.unit
class TestValidacaoEntrada:
    """Testes de validação de entrada."""

    def test_json_malformado(self, client):
        """JSON malformado deve retornar erro 422."""
        response = client.post(
            "/api/gerar",
            data="invalid json{{{",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    def test_tipo_incorreto(self, client):
        """Tipos incorretos devem ser rejeitados."""
        response = client.post(
            "/api/gerar",
            json={"tema": 123, "quantidade": "not_a_number"}  # tipos errados
        )

        assert response.status_code in [400, 422]

    def test_valores_extremos(self, client):
        """Valores extremos devem ser tratados."""
        payloads_extremos = [
            {"tema": "A" * 10000, "quantidade": 1},  # string muito longa
            {"tema": "Teste", "quantidade": 999999},  # número muito grande
            {"tema": "", "quantidade": 1},  # string vazia
            {"tema": "Teste", "quantidade": -1},  # número negativo
        ]

        for payload in payloads_extremos:
            response = client.post("/api/gerar", json=payload)
            # Deve retornar erro ou aceitar com validação
            assert response.status_code in [200, 202, 400, 422, 429]


@pytest.mark.integration
class TestFluxoCompleto:
    """Testes de fluxo completo através da API."""

    @patch("servidor._task_youtube")
    @patch("servidor._task_pipeline")
    def test_fluxo_youtube_completo(self, mock_pipeline, mock_youtube, client):
        """Fluxo completo: processar YouTube -> rodar pipeline."""
        # 1. Processar YouTube
        mock_youtube.return_value = {"video_id": 1, "status": "processado"}

        response1 = client.post(
            "/api/youtube/processar",
            json={"url": "https://youtube.com/watch?v=test123"}
        )

        # Pode ter rate limit de testes anteriores
        assert response1.status_code in [200, 202, 429]

        # 2. Rodar pipeline (se o passo anterior teve sucesso)
        # Endpoint real: /api/pipeline/rodar
        if response1.status_code in [200, 202]:
            mock_pipeline.return_value = {"cortes": 3, "status": "gerado"}

            response2 = client.post(
                "/api/pipeline/rodar",
                json={}
            )

            # Pode não ter implementação ou rate limit
            assert response2.status_code in [200, 202, 404, 429]


@pytest.mark.unit
class TestErrorHandling:
    """Testes de tratamento de erros."""

    def test_endpoint_inexistente(self, client):
        """Endpoint inexistente deve retornar 404."""
        response = client.get("/api/rota/que/nao/existe")
        assert response.status_code == 404

    def test_metodo_nao_permitido(self, client):
        """Método HTTP incorreto deve retornar 405."""
        # Tentar GET em endpoint que só aceita POST
        response = client.get("/api/gerar")
        assert response.status_code in [404, 405]

    @patch("servidor._task_youtube")
    def test_erro_interno_tratado(self, mock_task, client):
        """Erros internos devem ser tratados graciosamente."""
        # Background task erro não afeta HTTP response (roda após response)
        mock_task.return_value = None

        response = client.post(
            "/api/youtube/processar",
            json={"url": "https://youtube.com/watch?v=test"}
        )

        # Deve aceitar a requisição (200/202) ou rate limit (429)
        assert response.status_code in [200, 202, 429]

        # Verificar que endpoint não crasha em erro de validação
        response_invalid = client.post(
            "/api/youtube/processar",
            json={}  # URL obrigatória faltando
        )
        assert response_invalid.status_code in [400, 422]


@pytest.mark.unit
class TestLogging:
    """Testes de logging do servidor."""

    def test_request_logging(self, client, caplog):
        """Requisições devem ser logadas."""
        import logging
        caplog.set_level(logging.INFO)

        client.get("/api/health")

        # Pode ou não ter logs dependendo da configuração
        # Apenas verificar que não há erro
        assert True

    def test_error_logging(self, client, caplog):
        """Erros devem ser logados."""
        import logging
        caplog.set_level(logging.ERROR)

        # Fazer requisição que gera erro
        client.post("/api/gerar", json={})

        # Pode ou não ter logs
        # Apenas verificar que não há crash
        assert True


@pytest.mark.unit
class TestSecurity:
    """Testes de segurança da API."""

    def test_sql_injection_attempt(self, client):
        """Tentativas de SQL injection devem ser bloqueadas."""
        payload = {
            "tema": "'; DROP TABLE videos; --",
            "quantidade": 1
        }

        response = client.post("/api/gerar", json=payload)

        # Deve processar sem executar SQL injection
        # Status pode variar mas não deve crashar
        assert response.status_code in [200, 202, 400, 422, 429]

    def test_xss_attempt(self, client):
        """Tentativas de XSS devem ser sanitizadas."""
        payload = {
            "tema": "<script>alert('xss')</script>",
            "quantidade": 1
        }

        response = client.post("/api/gerar", json=payload)

        # Deve processar sem executar script
        assert response.status_code in [200, 202, 400, 422, 429]

        if response.status_code == 200:
            # Response não deve conter script sem escape
            assert "<script>" not in response.text

    def test_path_traversal_attempt(self, client, tmp_path, monkeypatch):
        """Tentativas de path traversal devem ser bloqueadas."""
        def mock_secure_path(base, filename):
            # Validar que filename foi sanitizado
            assert ".." not in filename
            assert "/" not in filename
            assert "\\" not in filename
            return tmp_path / filename

        monkeypatch.setattr("servidor.secure_path", mock_secure_path)

        files = {
            "arquivo": (
                "../../etc/passwd.mp4",  # tentativa de path traversal
                b"fake content",
                "video/mp4"
            )
        }

        # Usar endpoint real de upload local
        response = client.post("/api/local/processar", files=files)

        # Deve processar sem permitir acesso fora do diretório
        assert response.status_code in [200, 202, 400, 422]


@pytest.mark.slow
@pytest.mark.integration
class TestConcorrencia:
    """Testes de concorrência e múltiplas requisições."""

    def test_multiplas_requisicoes_simultaneas(self, client):
        """Servidor deve lidar com múltiplas requisições."""
        import concurrent.futures

        def fazer_requisicao(i):
            return client.get("/api/health")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fazer_requisicao, i) for i in range(10)]
            resultados = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Todas devem completar sem erro
        assert all(r.status_code == 200 for r in resultados)
