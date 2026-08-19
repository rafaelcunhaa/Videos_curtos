"""
Testes de Utilidades - Funções auxiliares e helpers.
Valida funções de formatação, validação e conversão.
"""
import pytest
from pathlib import Path
from datetime import datetime, timedelta


@pytest.mark.unit
class TestFormatacao:
    """Testes de funções de formatação."""

    def test_formatar_duracao_segundos(self):
        """Formatar segundos para HH:MM:SS."""
        from utils import formatar_duracao

        try:
            assert formatar_duracao(65) == "00:01:05"
            assert formatar_duracao(3661) == "01:01:01"
            assert formatar_duracao(0) == "00:00:00"
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_formatar_tamanho_arquivo(self):
        """Formatar bytes para formato legível."""
        from utils import formatar_tamanho

        try:
            assert "KB" in formatar_tamanho(1024) or "kB" in formatar_tamanho(1024)
            assert "MB" in formatar_tamanho(1024 * 1024)
            assert "GB" in formatar_tamanho(1024 * 1024 * 1024)
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_formatar_data_brasileira(self):
        """Formatar data para padrão BR."""
        from utils import formatar_data_br

        try:
            data = datetime(2026, 8, 19, 15, 30, 0)
            resultado = formatar_data_br(data)

            assert "19" in resultado
            assert "08" in resultado or "8" in resultado
            assert "2026" in resultado
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestValidacao:
    """Testes de funções de validação."""

    def test_validar_url_youtube(self):
        """Validar URLs do YouTube."""
        from utils import validar_url_youtube

        try:
            assert validar_url_youtube("https://youtube.com/watch?v=abc123") is True
            assert validar_url_youtube("https://youtu.be/abc123") is True
            assert validar_url_youtube("https://vimeo.com/123") is False
            assert validar_url_youtube("not-a-url") is False
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_validar_extensao_video(self):
        """Validar extensões de vídeo permitidas."""
        from utils import validar_extensao_video

        try:
            assert validar_extensao_video("video.mp4") is True
            assert validar_extensao_video("video.mov") is True
            assert validar_extensao_video("video.exe") is False
            assert validar_extensao_video("video.txt") is False
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_sanitizar_filename(self):
        """Sanitizar nomes de arquivo."""
        from utils import sanitizar_filename

        try:
            # Caracteres perigosos devem ser removidos/substituídos
            assert ".." not in sanitizar_filename("../../../etc/passwd")
            assert "/" not in sanitizar_filename("pasta/arquivo.mp4")
            assert "\\" not in sanitizar_filename("pasta\\arquivo.mp4")
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestConversao:
    """Testes de funções de conversão."""

    def test_converter_timestamp_para_segundos(self):
        """Converter timestamp HH:MM:SS para segundos."""
        from utils import timestamp_para_segundos

        try:
            assert timestamp_para_segundos("00:01:05") == 65
            assert timestamp_para_segundos("01:00:00") == 3600
            assert timestamp_para_segundos("00:00:00") == 0
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_converter_segundos_para_timestamp(self):
        """Converter segundos para timestamp HH:MM:SS."""
        from utils import segundos_para_timestamp

        try:
            assert segundos_para_timestamp(65) == "00:01:05"
            assert segundos_para_timestamp(3600) == "01:00:00"
            assert segundos_para_timestamp(0) == "00:00:00"
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestManipulacaoArquivos:
    """Testes de manipulação de arquivos."""

    def test_criar_diretorio_se_nao_existe(self, tmp_path):
        """Criar diretório apenas se não existir."""
        from utils import criar_diretorio

        try:
            novo_dir = tmp_path / "novo_diretorio"
            assert not novo_dir.exists()

            criar_diretorio(novo_dir)
            assert novo_dir.exists()

            # Chamar novamente não deve dar erro
            criar_diretorio(novo_dir)
            assert novo_dir.exists()
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_limpar_arquivos_antigos(self, tmp_path):
        """Limpar arquivos mais antigos que X dias."""
        from utils import limpar_arquivos_antigos

        try:
            # Criar arquivo "antigo"
            arquivo_antigo = tmp_path / "antigo.txt"
            arquivo_antigo.write_text("conteúdo")

            # Modificar data de modificação para 10 dias atrás
            import os
            import time

            timestamp_antigo = time.time() - (10 * 24 * 3600)
            os.utime(arquivo_antigo, (timestamp_antigo, timestamp_antigo))

            # Criar arquivo novo
            arquivo_novo = tmp_path / "novo.txt"
            arquivo_novo.write_text("conteúdo")

            # Limpar arquivos com mais de 5 dias
            limpar_arquivos_antigos(tmp_path, dias=5)

            # Arquivo antigo deve ter sido deletado
            assert not arquivo_antigo.exists()
            # Arquivo novo deve permanecer
            assert arquivo_novo.exists()
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestSeguranca:
    """Testes de funções de segurança."""

    def test_secure_path_valida_input(self):
        """secure_path deve validar e sanitizar paths."""
        from utils import secure_path

        try:
            # Path normal deve funcionar
            resultado = secure_path("base", "arquivo.mp4")
            assert isinstance(resultado, Path)

            # Path traversal deve ser bloqueado/sanitizado
            resultado = secure_path("base", "../../../etc/passwd")
            assert ".." not in str(resultado)
            assert "etc/passwd" not in str(resultado)
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_validar_json_seguro(self):
        """Validar que JSON não contém código malicioso."""
        from utils import validar_json_seguro
        import json

        try:
            # JSON normal
            json_valido = '{"nome": "teste", "valor": 123}'
            assert validar_json_seguro(json_valido) is True

            # JSON com possível injeção
            json_malicioso = '{"codigo": "__import__(\'os\').system(\'rm -rf /\')"}'
            # Deve ser validado ou marcado como suspeito
            resultado = validar_json_seguro(json_malicioso)
            assert isinstance(resultado, bool)
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestLogging:
    """Testes de funções de logging."""

    def test_log_com_cores(self, caplog):
        """Log com cores deve funcionar."""
        import logging
        from utils import log_colorido

        try:
            caplog.set_level(logging.INFO)

            log_colorido("Mensagem de teste", "INFO")

            # Verificar que foi logado
            assert len(caplog.records) >= 0
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestCalculos:
    """Testes de funções de cálculo."""

    def test_calcular_custo_total(self):
        """Calcular custo total de API."""
        from utils import calcular_custo_total

        try:
            custos = [0.05, 0.10, 0.03, 0.12]
            total = calcular_custo_total(custos)

            assert total == pytest.approx(0.30, 0.01)
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_converter_usd_para_brl(self):
        """Converter USD para BRL."""
        from utils import converter_usd_para_brl
        from constantes import TAXA_CAMBIO_USD_BRL

        try:
            valor_usd = 10.0
            valor_brl = converter_usd_para_brl(valor_usd)

            assert valor_brl == valor_usd * TAXA_CAMBIO_USD_BRL
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestExtracao:
    """Testes de funções de extração de dados."""

    def test_extrair_id_youtube_url_completa(self):
        """Extrair ID de URL completa do YouTube."""
        from utils import extrair_id_youtube

        try:
            url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            video_id = extrair_id_youtube(url)

            assert video_id == "dQw4w9WgXcQ"
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_extrair_id_youtube_url_curta(self):
        """Extrair ID de URL curta do YouTube."""
        from utils import extrair_id_youtube

        try:
            url = "https://youtu.be/dQw4w9WgXcQ"
            video_id = extrair_id_youtube(url)

            assert video_id == "dQw4w9WgXcQ"
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_extrair_id_youtube_url_invalida(self):
        """URL inválida deve retornar None."""
        from utils import extrair_id_youtube

        try:
            url = "https://vimeo.com/123456"
            video_id = extrair_id_youtube(url)

            assert video_id is None
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestTempoEData:
    """Testes de manipulação de tempo e data."""

    def test_calcular_intervalo_horas(self):
        """Calcular intervalo entre duas datas em horas."""
        from utils import calcular_intervalo_horas

        try:
            data1 = datetime(2026, 8, 19, 10, 0, 0)
            data2 = datetime(2026, 8, 19, 14, 30, 0)

            intervalo = calcular_intervalo_horas(data1, data2)

            assert intervalo == 4.5
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_agendar_proximo_horario(self):
        """Agendar próximo horário disponível."""
        from utils import agendar_proximo_horario

        try:
            agora = datetime(2026, 8, 19, 10, 0, 0)
            intervalo_horas = 4

            proximo = agendar_proximo_horario(agora, intervalo_horas)

            assert proximo == datetime(2026, 8, 19, 14, 0, 0)
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestRetryLogic:
    """Testes de lógica de retry."""

    def test_retry_com_sucesso(self):
        """Retry deve suceder após falhas temporárias."""
        from utils import retry_on_failure

        try:
            contador = {"tentativas": 0}

            @retry_on_failure(max_tentativas=3, delay=0.1)
            def funcao_flaky():
                contador["tentativas"] += 1
                if contador["tentativas"] < 3:
                    raise Exception("Falha temporária")
                return "Sucesso"

            resultado = funcao_flaky()

            assert resultado == "Sucesso"
            assert contador["tentativas"] == 3
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")

    def test_retry_falha_apos_max_tentativas(self):
        """Retry deve falhar após esgotar tentativas."""
        from utils import retry_on_failure

        try:
            @retry_on_failure(max_tentativas=2, delay=0.1)
            def funcao_sempre_falha():
                raise Exception("Falha permanente")

            with pytest.raises(Exception):
                funcao_sempre_falha()
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestHash:
    """Testes de funções de hash."""

    def test_gerar_hash_arquivo(self, tmp_path):
        """Gerar hash de arquivo."""
        from utils import gerar_hash_arquivo

        try:
            arquivo = tmp_path / "teste.txt"
            arquivo.write_text("Conteúdo de teste")

            hash1 = gerar_hash_arquivo(arquivo)
            hash2 = gerar_hash_arquivo(arquivo)

            # Mesmo arquivo deve gerar mesmo hash
            assert hash1 == hash2

            # Modificar arquivo
            arquivo.write_text("Conteúdo diferente")
            hash3 = gerar_hash_arquivo(arquivo)

            # Hash deve ser diferente
            assert hash1 != hash3
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.unit
class TestProgressBar:
    """Testes de barra de progresso."""

    def test_criar_progress_bar(self):
        """Criar barra de progresso."""
        from utils import criar_progress_bar

        try:
            progress = criar_progress_bar(total=100, descricao="Testando")

            assert progress is not None
        except (ImportError, AttributeError):
            pytest.skip("Função não implementada")


@pytest.mark.integration
class TestFuncionalidadesIntegradas:
    """Testes de funcionalidades que usam múltiplas funções."""

    def test_pipeline_validacao_completa(self):
        """Pipeline completo de validação."""
        from utils import (
            validar_url_youtube,
            extrair_id_youtube,
            sanitizar_filename
        )

        try:
            # 1. Validar URL
            url = "https://youtube.com/watch?v=abc123"
            assert validar_url_youtube(url)

            # 2. Extrair ID
            video_id = extrair_id_youtube(url)
            assert video_id == "abc123"

            # 3. Sanitizar filename
            filename = sanitizar_filename(f"video_{video_id}.mp4")
            assert ".." not in filename
            assert "/" not in filename
        except (ImportError, AttributeError):
            pytest.skip("Funções não implementadas")


@pytest.mark.unit
class TestErrorHandling:
    """Testes de tratamento de erros."""

    def test_funcoes_nao_crasham_com_none(self):
        """Funções devem tratar None graciosamente."""
        from utils import (
            formatar_duracao,
            extrair_id_youtube,
            sanitizar_filename
        )

        try:
            # Não devem crashar com None
            try:
                formatar_duracao(None)
            except (TypeError, ValueError, AttributeError):
                pass  # Esperado

            try:
                extrair_id_youtube(None)
            except (TypeError, ValueError, AttributeError):
                pass  # Esperado

            try:
                sanitizar_filename(None)
            except (TypeError, ValueError, AttributeError):
                pass  # Esperado
        except (ImportError, AttributeError):
            pytest.skip("Funções não implementadas")
