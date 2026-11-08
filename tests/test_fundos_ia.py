"""Testes locais SEM GPU/modelos: servidor ComfyUI falso + clipes sintéticos do FFmpeg.
Rodar na raiz do projeto:  python -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import comfyui_client as cc          # noqa: E402
import fundos_ia as fi               # noqa: E402
from config import cfg               # noqa: E402


def criar_clip(caminho: Path, dur: float = 4, w: int = 544, h: int = 960, cor="testsrc2"):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"{cor}=size={w}x{h}:rate=25:duration={dur}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(caminho)], check=True)
    return caminho


def probe(caminho: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height:format=duration", "-of", "json",
                        str(caminho)], capture_output=True, text=True)
    return json.loads(r.stdout)


class FakeComfy(BaseHTTPRequestHandler):
    video = b""
    prompts: list = []
    falhar = False
    pendentes = 0

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path.startswith("/system_stats"):
            self._json(200, {})
        elif self.path.startswith("/history/"):
            if FakeComfy.pendentes > 0:
                FakeComfy.pendentes -= 1
                return self._json(200, {})
            self._json(200, {"abc": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {"12": {"images": [
                    {"filename": "../evil/ceu_1_00001_.mp4", "subfolder": "", "type": "output"},
                    {"filename": "preview.mp4", "subfolder": "", "type": "temp"}],
                    "animated": [True]}}}})
        elif self.path.startswith("/view"):
            self.send_response(200)
            self.send_header("Content-Length", str(len(FakeComfy.video)))
            self.end_headers()
            self.wfile.write(FakeComfy.video)

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeComfy.prompts.append(corpo)
        if FakeComfy.falhar:
            return self._json(400, {"error": "node_errors"})
        self._json(200, {"prompt_id": "abc"})


class BaseServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        FakeComfy.video = criar_clip(cls.dir / "mock.mp4", dur=1).read_bytes()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeComfy)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        FakeComfy.prompts, FakeComfy.falhar, FakeComfy.pendentes = [], False, 0


class TestWorkflow(unittest.TestCase):
    def test_preencher_mantem_tipos(self):
        wf = {"a": {"w": "{{W}}", "t": "x {{P}} y", "l": ["1", 0]}}
        out = cc.preencher(wf, W=544, P="oi")
        self.assertEqual(out["a"], {"w": 544, "t": "x oi y", "l": ["1", 0]})

    def test_template_ltx_completo_e_ligacoes_validas(self):
        wf = cc.carregar_workflow(fi.WORKFLOW)
        cheio = cc.preencher(wf, CKPT="a", CLIP="b", PROMPT="p", NEGATIVE="n", SEED=1,
                             PREFIX="x", WIDTH=544, HEIGHT=960, FRAMES=97, FPS=25, STEPS=30)
        self.assertNotIn("{{", json.dumps(cheio))
        for no in cheio.values():
            for v in no["inputs"].values():
                if isinstance(v, list):
                    self.assertIn(v[0], cheio)


class TestCliente(BaseServidor):
    def test_executar_baixa_so_saida_final_e_sanitiza_nome(self):
        cli = cc.ComfyUI(self.url)
        self.assertTrue(cli.online())
        pasta = self.dir / "dl"
        arqs = cli.executar({"x": 1}, pasta)
        self.assertEqual([a.name for a in arqs], ["ceu_1_00001_.mp4"])   # sem ../ e sem preview
        self.assertEqual(arqs[0].parent, pasta)

    def test_aguardar_faz_polling(self):
        FakeComfy.pendentes = 2
        out = cc.ComfyUI(self.url).aguardar("abc", intervalo=0.01)
        self.assertIn("12", out)

    def test_http_400_vira_comfyerror(self):
        FakeComfy.falhar = True
        with self.assertRaises(cc.ComfyError):
            cc.ComfyUI(self.url).enviar({})

    def test_offline(self):
        self.assertFalse(cc.ComfyUI("http://127.0.0.1:9").online())


class TestGerarPool(BaseServidor):
    def _patch(self, nome):
        pasta = self.dir / nome
        return pasta, mock.patch.object(cfg, "pasta_fundos_ia", pasta), \
            mock.patch.object(cfg, "comfyui_url", self.url)

    def test_gera_n_clipes_com_prompt_e_seed_preenchidos(self):
        pasta, p1, p2 = self._patch("pool1")
        with p1, p2:
            gerados = fi.gerar_pool(n=2, tema="ceu")
        self.assertEqual(len(gerados), 2)
        self.assertTrue(all(g.parent == pasta / "ceu" for g in gerados))
        enviado = FakeComfy.prompts[0]["prompt"]
        self.assertEqual(enviado["6"]["inputs"]["width"], 544)
        self.assertIsInstance(enviado["9"]["inputs"]["noise_seed"], int)
        self.assertIn(enviado["3"]["inputs"]["text"], fi.PROMPTS["ceu"])

    def test_dry_run_nao_chama_servidor(self):
        _, p1, p2 = self._patch("pool2")
        with p1, p2:
            self.assertEqual(fi.gerar_pool(n=3, dry_run=True), [])
        self.assertEqual(FakeComfy.prompts, [])

    def test_travas(self):
        with self.assertRaises(ValueError):
            fi.gerar_pool(n=99)                       # acima do limite de custo
        with self.assertRaises(ValueError):
            fi.gerar_pool(n=1, tema="inexistente")

    def test_aborta_apos_falhas_seguidas(self):
        _, p1, p2 = self._patch("pool3")
        FakeComfy.falhar = True
        with p1, p2, self.assertRaises(cc.ComfyError):
            fi.gerar_pool(n=10, tema="luz")
        self.assertEqual(len(FakeComfy.prompts), fi.MAX_FALHAS_SEGUIDAS)


class TestComposicao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.clips = [criar_clip(cls.dir / f"c{i}.mp4", dur=4, cor=c)
                     for i, c in enumerate(["testsrc2", "smptebars", "testsrc", "rgbtestsrc"])]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sequencia_sem_vizinhos_repetidos_e_cobre_duracao(self):
        durs = {c: 4.0 for c in self.clips}
        seq = fi._sequencia(self.clips, durs, 60, 0.5)
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])))
        self.assertGreaterEqual(4 * len(seq) - 0.5 * (len(seq) - 1), 60)

    def test_compor_60s_vertical(self):
        saida = fi.compor_fundo(60, self.dir / "fundo60.mp4", self.clips)
        info = probe(saida)
        self.assertAlmostEqual(float(info["format"]["duration"]), 60, delta=0.2)
        v = info["streams"][0]
        self.assertEqual((v["width"], v["height"]), (544, 960))

    def test_compor_com_um_unico_clipe(self):
        saida = fi.compor_fundo(10, self.dir / "um.mp4", self.clips[:1])
        self.assertAlmostEqual(float(probe(saida)["format"]["duration"]), 10, delta=0.2)

    def test_obter_fundo_ia_nunca_levanta(self):
        with mock.patch.object(cfg, "pasta_fundos_ia", self.dir / "vazio"):
            self.assertIsNone(fi.obter_fundo_ia(10, self.dir))       # pool vazio
        ruim = self.dir / "ruim" / "x" / "quebrado.mp4"
        ruim.parent.mkdir(parents=True)
        ruim.write_bytes(b"nao e video")
        with mock.patch.object(cfg, "pasta_fundos_ia", self.dir / "ruim"):
            self.assertIsNone(fi.obter_fundo_ia(10, self.dir))       # clipe corrompido


class TestIntegracaoPipeline(unittest.TestCase):
    """montar_video() real (FFmpeg) com stubs das deps pesadas (edge_tts, anthropic...)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.cwd = os.getcwd()
        os.chdir(cls.dir)                       # logs/, fundos/ etc. ficam no tmp
        for nome, attrs in {"edge_tts": {},
                            "retry": {"chamar_anthropic": None, "chamar_elevenlabs": None},
                            "telegram": {"notificar": lambda *a, **k: None},
                            "analytics": {"obter_config_otimizada": lambda: {}}}.items():
            m = types.ModuleType(nome)
            m.__dict__.update(attrs)
            sys.modules.setdefault(nome, m)
        import gerador_conteudo as g
        cls.g = g
        cls.audio = cls.dir / "narracao.mp3"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=220:duration=61", str(cls.audio)], check=True)
        cls.clips = [criar_clip(cls.dir / "fundos_ia" / "ceu" / f"c{i}.mp4", cor=c)
                     for i, c in enumerate(["testsrc2", "smptebars", "testsrc"])]
        cls.dados = {"formato": "versiculo", "titulo_yt": "t", "descricao": "d",
                     "roteiro": "Primeira frase do roteiro. Segunda frase aqui. Terceira frase final."}

    @classmethod
    def tearDownClass(cls):
        import logging
        os.chdir(cls.cwd)
        logging.shutdown()
        cls.tmp.cleanup()

    def _montar(self, fundo_ia: bool, pasta_ia: Path):
        with mock.patch.object(cfg, "fundo_ia", fundo_ia), \
                mock.patch.object(cfg, "pasta_fundos_ia", pasta_ia):
            mp4, txt = self.g.montar_video(self.dados, self.audio, self.dir / "out")
        self.assertIsNotNone(mp4, "montar_video falhou")
        info = probe(mp4)
        tipos = [s["codec_type"] for s in info["streams"]]
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        self.assertEqual((v["width"], v["height"]), (1080, 1920))
        self.assertIn("audio", tipos)
        self.assertAlmostEqual(float(info["format"]["duration"]), 61.5, delta=1.0)

    def test_com_fundo_ia_gera_video_vertical_60s(self):
        # wraps: executa de verdade, mas prova que o fundo IA foi usado (não o fallback)
        with mock.patch.object(self.g, "log", wraps=self.g.log), \
                mock.patch("fundos_ia.compor_fundo", wraps=fi.compor_fundo) as compor:
            self._montar(True, self.dir / "fundos_ia")
            compor.assert_called_once()
            self.assertGreaterEqual(compor.call_args.args[0], 61)   # duração do áudio

    def test_fundo_ia_ligado_com_pool_vazio_faz_fallback(self):
        with mock.patch.object(self.g, "log", wraps=self.g.log):
            self._montar(True, self.dir / "pool_inexistente")

    def test_fundo_ia_desligado_mantem_comportamento_atual(self):
        with mock.patch.object(self.g, "log", wraps=self.g.log), \
                mock.patch("fundos_ia.compor_fundo") as compor:
            self._montar(False, self.dir / "fundos_ia")
            compor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
