"""
Testes de Utilidades - Funções auxiliares e helpers.
Valida funções de formatação, validação e conversão.
As funções testadas devem permanecer alinhadas às exportações públicas de `utils.py`.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.mark.unit
class TestFormatacao:
    """Testes de funções de formatação."""

    def test_obter_duracao_existe(self):
        """obter_duracao deve existir e ser chamável."""
        from utils import obter_duracao

        assert callable(obter_duracao)

    def test_obter_duracao_arquivo_inexistente_retorna_zero(self):
        """obter_duracao deve retornar 0.0 para arquivo inexistente (não None)."""
        from utils import obter_duracao

        assert obter_duracao("/caminho/inexistente.mp4") == 0.0

    def test_t2ass_conversao(self):
        """t2ass deve converter segundos para formato ASS."""
        from utils import t2ass

        assert t2ass(65.0) == "0:01:05.00"
        assert t2ass(3661.0) == "1:01:01.00"
        assert t2ass(0.0) == "0:00:00.00"
        assert t2ass(1.5) == "0:00:01.50"

    def test_t2ass_valores_negativos(self):
        """t2ass deve tratar negativos como zero."""
        from utils import t2ass

        assert t2ass(-1.0) == "0:00:00.00"
        assert t2ass(-100.0) == "0:00:00.00"


@pytest.mark.unit
class TestValidacao:
    """Testes de funções de validação."""

    def test_validar_extensao_video_via_constantes(self):
        """Constantes devem conter EXTENSOES_VIDEO_VALIDAS."""
        from constantes import EXTENSOES_VIDEO_VALIDAS

        assert ".mp4" in EXTENSOES_VIDEO_VALIDAS
        assert ".mov" in EXTENSOES_VIDEO_VALIDAS
        assert ".avi" in EXTENSOES_VIDEO_VALIDAS

    def test_youtube_url_regex_via_constantes(self):
        """Constantes devem conter YOUTUBE_URL_REGEX."""
        import re

        from constantes import YOUTUBE_URL_REGEX

        pattern = re.compile(YOUTUBE_URL_REGEX)
        assert pattern.match("https://youtube.com/watch?v=abc123")
        assert pattern.match("https://youtu.be/abc123")
        assert pattern.match("https://www.youtube.com/shorts/abc123")
        assert not pattern.match("https://vimeo.com/123456")

    def test_parse_json_robusto(self):
        """parse_json_robusto deve parsear JSON válido."""
        from utils import parse_json_robusto

        resultado = parse_json_robusto('{"chave": "valor", "num": 42}')
        assert resultado == {"chave": "valor", "num": 42}

    def test_parse_json_robusto_com_texto_extra(self):
        """parse_json_robusto deve extrair JSON de texto com lixo."""
        from utils import parse_json_robusto

        texto = 'Aqui tem um JSON: {"ok": true} e mais texto'
        resultado = parse_json_robusto(texto)
        assert resultado == {"ok": True}

    def test_parse_json_robusto_remove_markdown(self):
        """parse_json_robusto deve remover markdown fences."""
        from utils import parse_json_robusto

        texto = '```json\n{"teste": 123}\n```'
        resultado = parse_json_robusto(texto)
        assert resultado == {"teste": 123}

    def test_parse_json_robusto_invalido(self):
        """parse_json_robusto deve lançar ValueError para JSON inválido."""
        from utils import parse_json_robusto

        with pytest.raises(ValueError):
            parse_json_robusto('{"invalido": }')


@pytest.mark.unit
class TestConversao:
    """Testes de conversão de unidades."""

    def test_calcular_custo_claude(self):
        """calcular_custo_claude deve calcular custo baseado em objeto usage."""
        from utils import calcular_custo_claude

        class MockUsage:
            input_tokens = 1000
            output_tokens = 500

        custo = calcular_custo_claude(MockUsage())
        assert isinstance(custo, float)
        assert custo > 0

    def test_calcular_custo_claude_valores_conhecidos(self):
        """calcular_custo_claude com valores conhecidos (Sonnet 4: $3/M in, $15/M out)."""
        from utils import calcular_custo_claude

        class MockUsage:
            input_tokens = 1_000_000
            output_tokens = 1_000_000

        custo = calcular_custo_claude(MockUsage())
        # 3 + 15 = 18 USD por milhão
        assert abs(custo - 18.0) < 0.01


@pytest.mark.unit
class TestManipulacaoArquivos:
    """Testes de manipulação de arquivos."""

    def test_nome_seguro(self):
        """nome_seguro deve remover caracteres perigosos e substituir espaços por _."""
        from utils import nome_seguro

        assert nome_seguro("arquivo normal.mp4") == "arquivo_normal.mp4"
        assert nome_seguro("arquivo/perigoso.mp4") == "arquivoperigoso.mp4"
        assert nome_seguro('arquivo"com"aspas.mp4') == "arquivocomaspas.mp4"
        assert nome_seguro("arquivo:com:dois:pontos.mp4") == "arquivocomdoispontos.mp4"

    def test_nome_seguro_trunca_longo(self):
        """nome_seguro deve truncar nomes longos."""
        from utils import nome_seguro

        nome_longo = "a" * 50 + ".mp4"
        resultado = nome_seguro(nome_longo, max_len=20)
        assert len(resultado) <= 20

    def test_salvar_txt_publicacao(self):
        """salvar_txt_publicacao deve criar arquivo de publicação válido."""
        from utils import salvar_txt_publicacao

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "publicacao.txt"
            corte_info = {
                "titulo": "Teste",
                "gancho": "Hook",
                "duracao": 45,
                "tipo": "denso",
            }
            dados = {
                "titulo_yt": "Título YT",
                "titulo_tiktok": "Título TT",
                "descricao": "Descrição teste",
                "hashtags": ["#tag1", "#tag2"],
                "roteiro": "Roteiro completo",
            }
            salvar_txt_publicacao(caminho, dados, corte_info)
            assert caminho.exists()
            conteudo = caminho.read_text(encoding="utf-8")
            assert "Título YT" in conteudo
            assert "Título TT" in conteudo
            assert "#tag1 #tag2" in conteudo
            assert "TIPO: denso" in conteudo
            assert "DURAÇÃO: 45s" in conteudo

    def test_salvar_txt_publicacao_sem_corte_info(self):
        """salvar_txt_publicacao deve funcionar sem corte_info (usa dados)."""
        from utils import salvar_txt_publicacao

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "pub.txt"
            dados = {
                "titulo_yt": "Titulo Direto",
                "descricao": "Desc",
                "hashtags": ["#tag"],
                "formato": "historia",
                "roteiro": "Roteiro longo aqui...",
            }
            salvar_txt_publicacao(caminho, dados, None)
            assert caminho.exists()
            conteudo = caminho.read_text(encoding="utf-8")
            assert "Titulo Direto" in conteudo
            assert "TIPO: historia" in conteudo


@pytest.mark.unit
class TestSeguranca:
    """Testes de segurança."""

    def test_parse_json_robusto_nao_executa_codigo(self):
        """parse_json_robusto não deve executar código injetado - apenas parse JSON."""
        from utils import parse_json_robusto

        # String que parece JSON mas tem tentativa de injeção (não é JSON válido)
        texto_malicioso = "{\"codigo\": \"__import__('os').system('rm -rf /')\"}"
        # Não deve crashar o processo, deve lançar ValueError ou retornar dict seguro
        try:
            resultado = parse_json_robusto(texto_malicioso)
            assert isinstance(resultado, dict)
        except ValueError:
            pass  # Esperado para JSON malformado


@pytest.mark.unit
class TestCalculos:
    """Testes de cálculos financeiros."""

    def test_taxa_cambio_constantes(self):
        """TAXA_CAMBIO_USD_BRL deve estar definida."""
        from constantes import TAXA_CAMBIO_USD_BRL

        assert isinstance(TAXA_CAMBIO_USD_BRL, (int, float))
        assert TAXA_CAMBIO_USD_BRL > 0


@pytest.mark.unit
class TestExtracao:
    """Testes de extração de IDs e metadados."""

    def test_extrair_youtube_id_via_banco(self):
        """extrair_youtube_id deve funcionar via banco.py."""
        from banco import extrair_youtube_id

        assert extrair_youtube_id("https://youtu.be/abc123XYZ78") == "abc123XYZ78"
        assert (
            extrair_youtube_id("https://youtube.com/watch?v=abc123XYZ78")
            == "abc123XYZ78"
        )
        assert (
            extrair_youtube_id("https://youtube.com/shorts/abc123XYZ78")
            == "abc123XYZ78"
        )
        assert extrair_youtube_id("abc123XYZ78") == "abc123XYZ78"


@pytest.mark.unit
class TestTempoEData:
    """Testes de tempo e data."""

    def test_constantes_duracao(self):
        """Constantes de duração devem estar definidas."""
        from constantes import DURACAO_MAX_GLOBAL, DURACAO_MIN_GLOBAL

        assert DURACAO_MIN_GLOBAL == 30
        assert DURACAO_MAX_GLOBAL == 59
        assert DURACAO_MIN_GLOBAL < DURACAO_MAX_GLOBAL


@pytest.mark.unit
class TestRetryLogic:
    """Testes de lógica de retry."""

    def test_chamar_anthropic_existe(self):
        """retry.chamar_anthropic deve existir."""
        from retry import chamar_anthropic

        assert callable(chamar_anthropic)

    def test_chamar_elevenlabs_existe(self):
        """retry.chamar_elevenlabs deve existir."""
        from retry import chamar_elevenlabs

        assert callable(chamar_elevenlabs)

    def test_chamar_youtube_existe(self):
        """retry.chamar_youtube deve existir."""
        from retry import chamar_youtube

        assert callable(chamar_youtube)


@pytest.mark.unit
class TestHash:
    """Testes de hash - não implementado em utils, pular."""

    def test_hash_placeholder(self):
        pytest.skip("Hash não implementado em utils.py")


@pytest.mark.unit
class TestProgressBar:
    """Testes de progress bar - não implementado em utils, pular."""

    def test_progress_bar_placeholder(self):
        pytest.skip("Progress bar não implementado em utils.py")


@pytest.mark.unit
class TestFuncionalidadesIntegradas:
    """Testes de funcionalidades integradas."""

    def test_pipeline_validacao_completa(self):
        """Pipeline: validar extensão -> parse JSON -> salvar txt."""
        from constantes import EXTENSOES_VIDEO_VALIDAS
        from utils import parse_json_robusto, salvar_txt_publicacao

        with tempfile.TemporaryDirectory() as tmp:
            # 1. Validar extensão
            assert ".mp4" in EXTENSOES_VIDEO_VALIDAS
            # 2. Parse JSON
            dados = parse_json_robusto('{"titulo_yt": "Teste", "hashtags": ["#a"]}')
            assert dados["titulo_yt"] == "Teste"
            # 3. Salvar txt
            caminho = Path(tmp) / "pub.txt"
            corte_info = {
                "titulo": "Teste",
                "gancho": "Hook",
                "duracao": 30,
                "tipo": "denso",
            }
            salvar_txt_publicacao(caminho, dados, corte_info)
            assert caminho.exists()


@pytest.mark.unit
class TestErrorHandling:
    """Testes de tratamento de erro."""

    def test_funcoes_nao_crasham_com_entradas_invalidas(self):
        """Funções devem lidar graciosamente com None/entradas inválidas."""
        from utils import nome_seguro, obter_duracao, parse_json_robusto, t2ass

        # obter_duracao com None/path inexistente
        assert obter_duracao(None) == 0.0
        assert obter_duracao("") == 0.0
        assert obter_duracao("/inexistente.mp4") == 0.0

        # t2ass com valores extremos
        assert t2ass(-1) == "0:00:00.00"
        assert t2ass(0) == "0:00:00.00"

        # nome_seguro com None
        assert nome_seguro(None) in ("None", "")

        # parse_json_robusto com None
        try:
            parse_json_robusto(None)
        except (TypeError, ValueError, AttributeError):
            pass  # Esperado


# ============================
# Testes de integração (slow)
# ============================
@pytest.mark.integration
@pytest.mark.slow
class TestIntegracaoUtils:
    """Testes que requerem arquivos reais."""

    def test_obter_duracao_video_real(self, video_fake):
        """obter_duracao com bytes fake deve retornar 0.0 (graceful fail)."""
        from utils import obter_duracao

        # video_fake é apenas bytes (não vídeo válido), ffprobe não consegue parsear.
        # A função deve tratar isso graciosamente retornando 0.0.
        duracao = obter_duracao(video_fake)
        assert duracao == 0.0

    def test_obter_duracao_arquivo_inexistente(self, tmp_path):
        """obter_duracao com arquivo inexistente deve retornar 0.0 sem crashar."""
        from utils import obter_duracao

        caminho_inexistente = tmp_path / "video_que_nao_existe.mp4"
        assert obter_duracao(caminho_inexistente) == 0.0
