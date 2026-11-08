#!/usr/bin/env python3
"""
Cliente mínimo da API HTTP do ComfyUI (somente `requests`, sem websocket).

    cli = ComfyUI("http://127.0.0.1:8188")
    wf  = preencher(carregar_workflow("comfy_workflows/ltx_t2v.json"),
                    PROMPT="...", SEED=1)
    arquivos = cli.executar(wf, Path("saida"))

Funciona igual contra ComfyUI local ou numa GPU remota (RunPod, Vast, etc.).
Se houver proxy com autenticação na frente, passe `token` (Bearer).
"""
import json
import time
import uuid 
from pathlib import Path

import requests

EXT_VIDEO = {".mp4", ".webm", ".mov", ".mkv"}


class ComfyError(RuntimeError):
    pass


def carregar_workflow(caminho) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def preencher(obj, **vars):
    """Substitui "{{CHAVE}}" no workflow. Valor que é só o placeholder mantém
    o tipo original (int/float); placeholder dentro de texto vira str."""
    if isinstance(obj, dict):
        return {k: preencher(v, **vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [preencher(v, **vars) for v in obj]
    if isinstance(obj, str):
        for k, v in vars.items():
            marca = "{{%s}}" % k
            if obj == marca:
                return v
            if marca in obj:
                obj = obj.replace(marca, str(v))
    return obj


class ComfyUI:
    def __init__(self, url: str = "http://127.0.0.1:8188", token: str = "",
                 timeout: int = 30):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex
        self.s = requests.Session()
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    def online(self) -> bool:
        try:
            return self.s.get(f"{self.url}/system_stats", timeout=5).ok
        except requests.RequestException:
            return False

    def enviar(self, workflow: dict) -> str:
        r = self.s.post(f"{self.url}/prompt", timeout=self.timeout,
                        json={"prompt": workflow, "client_id": self.client_id})
        if r.status_code != 200:
            # 400 traz o motivo (node inexistente, modelo ausente, etc.)
            raise ComfyError(f"/prompt HTTP {r.status_code}: {r.text[:400]}")
        return r.json()["prompt_id"]

    def aguardar(self, prompt_id: str, limite_s: int = 900,
                 intervalo: float = 2.0) -> dict:
        fim = time.monotonic() + limite_s
        while time.monotonic() < fim:
            r = self.s.get(f"{self.url}/history/{prompt_id}", timeout=self.timeout)
            r.raise_for_status()
            h = r.json().get(prompt_id)
            if h:
                st = h.get("status", {})
                if st.get("status_str") == "error":
                    raise ComfyError(f"Execução falhou: {json.dumps(st)[:400]}")
                if st.get("completed"):
                    return h.get("outputs", {})
            time.sleep(intervalo)
        raise ComfyError(f"Timeout ({limite_s}s) aguardando {prompt_id}")

    def baixar_saidas(self, outputs: dict, pasta: Path) -> list[Path]:
        """Baixa os vídeos finais (type=output) listados no histórico."""
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        baixados = []
        for no in outputs.values():
            for itens in no.values():
                if not isinstance(itens, list):
                    continue
                for it in itens:
                    if not (isinstance(it, dict) and "filename" in it):
                        continue
                    nome = Path(it["filename"]).name  # nunca confiar em caminho do servidor
                    if Path(nome).suffix.lower() not in EXT_VIDEO:
                        continue
                    if it.get("type", "output") != "output":
                        continue
                    r = self.s.get(f"{self.url}/view", stream=True, timeout=120,
                                   params={"filename": nome,
                                           "subfolder": it.get("subfolder", ""),
                                           "type": "output"})
                    r.raise_for_status()
                    destino = pasta / nome
                    with open(destino, "wb") as f:
                        for chunk in r.iter_content(1024 * 256):
                            f.write(chunk)
                    baixados.append(destino)
        return baixados

    def executar(self, workflow: dict, pasta: Path, limite_s: int = 900) -> list[Path]:
        pid = self.enviar(workflow)
        saidas = self.aguardar(pid, limite_s=limite_s)
        arquivos = self.baixar_saidas(saidas, pasta)
        if not arquivos:
            raise ComfyError("Workflow terminou sem nenhum vídeo de saída")
        return arquivos
