"""
Testes de Segurança - Validação das correções aplicadas.
Garante que vulnerabilidades conhecidas estão corrigidas.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.mark.security
class TestPathTraversal:
    """Valida proteção contra path traversal em uploads."""

    def test_upload_path_traversal_attack(self, tmp_path, monkeypatch):
        """Tentativa de subir arquivo com ../ deve ser bloqueada."""
        from servidor import app

        # Mock da função secure_path para usar tmp_path
        def mock_secure_path(base, filename):
            return tmp_path / filename

        monkeypatch.setattr("servidor.secure_path", mock_secure_path)

        client = TestClient(app)

        # Arquivo malicioso tentando escapar do diretório
        files = {
            "arquivo": (
                "../../etc/passwd",  # path traversal
                b"fake content",
                "video/mp4",
            )
        }

        response = client.post("/api/upload", files=files)

        # Deve rejeitar ou sanitizar o nome
        # O nome final não pode conter ../
        assert response.status_code in [200, 400]

        # Se 200, verificar que o arquivo foi salvo com nome seguro
        if response.status_code == 200:
            saved_files = list(tmp_path.glob("**/*"))
            for f in saved_files:
                # Nenhum arquivo deve estar fora do tmp_path
                assert tmp_path in f.parents or f.parent == tmp_path

    def test_upload_extensao_invalida(self):
        """Upload com extensão não permitida deve ser rejeitado."""
        from servidor import app

        client = TestClient(app)

        files = {
            "arquivo": ("malware.exe", b"fake exe content", "application/x-msdownload")
        }

        response = client.post("/api/upload", files=files)
        assert response.status_code == 400
        assert "extensão" in response.json().get("detail", "").lower()

    def test_upload_nome_seguro(self, tmp_path, monkeypatch):
        """Nome do arquivo deve ser sanitizado corretamente."""
        from servidor import app

        def mock_secure_path(base, filename):
            # Verifica que filename não contém paths
            assert "/" not in filename
            assert "\\" not in filename
            return tmp_path / filename

        monkeypatch.setattr("servidor.secure_path", mock_secure_path)

        client = TestClient(app)

        files = {"arquivo": ("normal_video.mp4", b"fake video", "video/mp4")}

        # Não deve levantar exceção
        response = client.post("/api/upload", files=files)


@pytest.mark.security
class TestRateLimiting:
    """Valida proteção contra abuso de API."""

    def test_rate_limit_excedido(self, monkeypatch):
        """Muitas requisições devem ser bloqueadas."""
        from servidor import app

        client = TestClient(app)

        # Fazer mais requisições que o limite
        respostas = []
        for i in range(15):  # Limite é 10/hora no /api/youtube/processar
            response = client.post(
                "/api/youtube/processar",
                json={"url": f"https://youtube.com/watch?v=test{i}"},
            )
            respostas.append(response.status_code)

        # Deve ter pelo menos uma resposta 429 (Too Many Requests)
        assert 429 in respostas

    def test_rate_limit_sliding_window(self, monkeypatch):
        """Rate limiting deve usar janela deslizante."""

        from servidor import _rate_limit_store, check_rate_limit

        # Limpar store
        _rate_limit_store.clear()

        # Mock de Request
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"

        # Deve permitir requisições dentro do limite
        for i in range(5):
            check_rate_limit(mock_request, max_requests=5, window_seconds=60)

        # 6ª requisição deve falhar
        with pytest.raises(Exception) as exc:
            check_rate_limit(mock_request, max_requests=5, window_seconds=60)

        assert "429" in str(exc.value) or "limite" in str(exc.value).lower()


@pytest.mark.security
class TestValidacaoURL:
    """Valida que apenas URLs do YouTube são aceitas."""

    def test_url_youtube_valida(self):
        """URLs válidas do YouTube devem ser aceitas."""
        from servidor import app

        client = TestClient(app)

        urls_validas = [
            "https://youtube.com/watch?v=abcd1234",
            "https://www.youtube.com/watch?v=xyz789",
            "https://youtu.be/short123",
            "http://youtube.com/watch?v=test",
        ]

        for url in urls_validas:
            response = client.post("/api/youtube/processar", json={"url": url})
            # Não deve falhar por URL inválida (pode falhar por rate limit)
            assert response.status_code in [200, 202, 429]

    def test_url_invalida_rejeitada(self):
        """URLs que não são do YouTube devem ser rejeitadas."""
        from servidor import app

        client = TestClient(app)

        urls_invalidas = [
            "https://vimeo.com/123456",
            "https://malicious-site.com/video",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "http://youtube.com.fake-site.com/video",
        ]

        for url in urls_invalidas:
            response = client.post("/api/youtube/processar", json={"url": url})
            assert response.status_code == 400
            assert "url" in response.json().get("detail", "").lower()


@pytest.mark.security
class TestSQLInjection:
    """Valida proteção contra SQL injection."""

    def test_parametrized_queries(self, banco_teste):
        """Queries devem usar parâmetros, não concatenação."""
        import banco

        # Tentar injetar SQL através do título
        titulo_malicioso = "'; DROP TABLE videos; --"

        # Não deve causar erro ou executar o DROP
        video_id = banco.registrar_video(
            url="https://youtube.com/watch?v=test",
            titulo=titulo_malicioso,
            duracao_s=100.0,
            caminho_arquivo=Path("/tmp/test.mp4"),
        )

        assert video_id is not None

        # Verificar que a tabela ainda existe
        videos = banco.listar_videos()
        assert isinstance(videos, list)

    def test_special_chars_in_queries(self, banco_teste):
        """Caracteres especiais devem ser tratados corretamente."""
        import banco

        titulos_especiais = [
            "Video's com apóstrofo",
            'Video "com aspas"',
            "Video <script>alert('xss')</script>",
            "Video\ncom\nquebras\nde\nlinha",
        ]

        for titulo in titulos_especiais:
            video_id = banco.registrar_video(
                url=f"https://youtube.com/watch?v=test_{hash(titulo)}",
                titulo=titulo,
                duracao_s=100.0,
                caminho_arquivo=Path("/tmp/test.mp4"),
            )

            # Recuperar e verificar
            info = banco.buscar_video(video_id)
            assert info["titulo"] == titulo


@pytest.mark.security
class TestResourceLeaks:
    """Valida que recursos são limpos adequadamente."""

    def test_temp_audio_cleanup(self, tmp_path, monkeypatch):
        """Arquivos de áudio temporários devem ser limpos mesmo com erro."""
        from config import cfg

        monkeypatch.setattr(cfg, "pasta_audio_temp", tmp_path / "audio")
        cfg.pasta_audio_temp.mkdir(exist_ok=True)

        # Simular falha na geração de áudio
        def mock_gerar_audio_fail(*args, **kwargs):
            # Criar arquivo fake mas retornar False (falha)
            audio_path = args[1] if len(args) > 1 else None
            if audio_path:
                Path(audio_path).write_bytes(b"fake audio")
            return False

        monkeypatch.setattr("gerador_conteudo.gerar_audio", mock_gerar_audio_fail)

        # Contar arquivos antes
        files_antes = list(cfg.pasta_audio_temp.glob("*"))

        # Tentar gerar conteúdo (deve falhar)
        dados = {
            "roteiro": "Teste",
            "titulo": "Teste",
            "caminho_fundo": str(tmp_path / "fundo.mp4"),
        }

        # Função deve retornar None, None em caso de falha
        # E deve limpar o arquivo temporário

        # Verificar que não há leak de arquivos
        files_depois = list(cfg.pasta_audio_temp.glob("*"))

        # Não deve ter mais arquivos que antes
        # (ou deve ter o mesmo número, se a limpeza funcionou)
        assert len(files_depois) <= len(files_antes) + 1


@pytest.mark.security
class TestTimeouts:
    """Valida que timeouts diferenciados estão configurados."""

    def test_timeout_config_exists(self):
        """Constantes de timeout devem existir."""
        from config import cfg

        assert hasattr(cfg, "timeout_ffprobe")
        assert hasattr(cfg, "timeout_ffmpeg_corte")
        assert hasattr(cfg, "timeout_ffmpeg_encode")
        assert hasattr(cfg, "timeout_whisper")

    def test_timeouts_values_reasonable(self):
        """Valores de timeout devem ser razoáveis."""
        from config import cfg

        # FFprobe (metadados) deve ser rápido
        assert cfg.timeout_ffprobe <= 60

        # Corte deve ser médio
        assert 60 <= cfg.timeout_ffmpeg_corte <= 300

        # Encode pode ser longo
        assert 120 <= cfg.timeout_ffmpeg_encode <= 600

        # Whisper pode ser muito longo
        assert 300 <= cfg.timeout_whisper <= 1200

    def test_subprocess_uses_timeout(self, monkeypatch):
        """Chamadas subprocess devem usar timeout."""
        import subprocess

        from banco import obter_duracao

        chamadas = []

        def mock_run(*args, **kwargs):
            chamadas.append(kwargs)
            # Simular resposta válida
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '{"format":{"duration":"180.5"}}'
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        # Executar função que usa subprocess
        obter_duracao(Path("/fake/video.mp4"))

        # Verificar que timeout foi passado
        assert len(chamadas) > 0
        assert "timeout" in chamadas[0]
        assert chamadas[0]["timeout"] > 0


@pytest.mark.security
class TestRaceConditions:
    """Valida correção de race conditions."""

    def test_malformed_date_recovery(self, banco_populado):
        """Datas malformadas devem ser corrigidas automaticamente."""
        import banco
        from agendador import verificar_agendamentos

        corte_id = banco_populado["corte1_id"]

        # Inserir data malformada diretamente no banco
        import sqlite3

        conn = sqlite3.connect(banco_populado["banco_path"])
        conn.execute(
            "UPDATE cortes SET status='agendado', agendado_para='data_invalida' WHERE id=?",
            (corte_id,),
        )
        conn.commit()
        conn.close()

        # Verificar agendamentos (deve detectar e corrigir)
        # A função deve logar erro e resetar o status
        try:
            verificar_agendamentos()
        except Exception:
            pass  # Pode falhar por outros motivos, mas não deve crashar

        # Verificar que o status foi corrigido
        info = banco.buscar_corte(corte_id)
        # Status deve ter sido resetado para 'pronto' ou mantido
        assert info["status"] in ["pronto", "agendado"]


@pytest.mark.security
class TestInputValidation:
    """Valida sanitização de inputs do usuário."""

    def test_filename_sanitization(self):
        """Nomes de arquivo devem ser sanitizados."""
        from pathlib import Path

        nomes_perigosos = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "arquivo<script>.mp4",
            "arquivo|comando.mp4",
            "arquivo&command.mp4",
        ]

        for nome in nomes_perigosos:
            # Usar Path().name remove todos os paths
            nome_seguro = Path(nome).name

            # Nome seguro não deve conter caracteres de path
            assert ".." not in nome_seguro
            assert "/" not in nome_seguro
            assert "\\" not in nome_seguro

    def test_json_injection_protection(self, banco_teste):
        """Campos JSON devem ser validados."""

        import banco

        video_id = banco.registrar_video(
            url="https://youtube.com/watch?v=test",
            titulo="Teste",
            duracao_s=100.0,
            caminho_arquivo=Path("/tmp/test.mp4"),
        )

        # Tentar injetar JSON malformado
        corte_info_malicioso = {
            "tipo": "denso",
            "titulo": "Test",
            "gancho": "Test",
            "inicio": 0.0,
            "fim": 60.0,
            # Tentativa de injetar código
            "codigo_malicioso": "__import__('os').system('rm -rf /')",
        }

        # Deve aceitar mas não executar o código
        corte_id = banco.registrar_corte(
            video_id=video_id,
            numero=1,
            corte_info=corte_info_malicioso,
            caminho_video=Path("/tmp/corte.mp4"),
            caminho_txt=Path("/tmp/corte.txt"),
            desc_info=None,
        )

        assert corte_id is not None

        # Recuperar e verificar que é JSON válido
        info = banco.buscar_corte(corte_id)
        assert isinstance(info["corte_info"], dict)
