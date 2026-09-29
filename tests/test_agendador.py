"""Testes do agendador contra as APIs atualmente públicas."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest


def _corte(corte_id, banco):
    return next(c for c in banco.listar_cortes() if c["id"] == corte_id)


@pytest.mark.unit
def test_agendar_corte_automatico_atualiza_status_e_data(banco_populado):
    import agendador
    import banco

    data = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    resultado = agendador.agendar_corte_automatico(
        banco_populado["corte1_id"], data_hora_str=data
    )
    corte = _corte(banco_populado["corte1_id"], banco)

    assert resultado is not None
    assert corte["status"] == "agendado"
    assert corte["agendado_para"].startswith(data)


@pytest.mark.unit
def test_agendar_corte_automatico_rejeita_data_invalida(banco_populado):
    import agendador
    import banco

    resultado = agendador.agendar_corte_automatico(
        banco_populado["corte1_id"], data_hora_str="data-invalida"
    )
    corte = _corte(banco_populado["corte1_id"], banco)

    assert resultado is None
    assert corte["status"] == "pronto"


@pytest.mark.unit
def test_listar_cortes_agendados_mantem_ordem_cronologica(banco_populado):
    import banco

    agora = datetime.now()
    conn = sqlite3.connect(banco_populado["banco_path"])
    for corte_id, horas in (
        (banco_populado["corte1_id"], 2),
        (banco_populado["corte2_id"], 1),
    ):
        conn.execute(
            "UPDATE cortes SET status='agendado', agendado_para=? WHERE id=?",
            ((agora + timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S"), corte_id),
        )
    conn.commit()
    conn.close()

    cortes = banco.listar_cortes(status="agendado")
    assert [c["id"] for c in cortes] == [
        banco_populado["corte2_id"],
        banco_populado["corte1_id"],
    ]


@pytest.mark.unit
def test_postar_agora_falha_sem_corte(banco_teste):
    import agendador

    assert agendador.postar_agora(999999) is False


@pytest.mark.unit
def test_verificar_e_postar_agendados_processa_upload(banco_populado):
    import agendador
    import banco

    corte_id = banco_populado["corte1_id"]
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(banco_populado["banco_path"])
    conn.execute(
        "UPDATE cortes SET status='agendado', agendado_para=? WHERE id=?",
        (agora, corte_id),
    )
    conn.commit()
    conn.close()

    with (
        patch.object(agendador, "fazer_upload", return_value="abc123"),
        patch.object(agendador, "fazer_upload_tiktok"),
        patch.object(agendador.notificar, "short_postado"),
        patch.object(agendador, "excluir_video_local"),
        patch.object(agendador.time, "sleep"),
    ):
        agendador.verificar_e_postar_agendados()

    assert _corte(corte_id, banco)["status"] == "postado"


@pytest.mark.unit
def test_excluir_video_local_remove_arquivo(tmp_path):
    from agendador import excluir_video_local

    caminho = tmp_path / "video.mp4"
    caminho.write_bytes(b"video")
    excluir_video_local(str(caminho))
    assert not caminho.exists()


@pytest.mark.unit
def test_excluir_video_local_ignora_caminho_ausente():
    from agendador import excluir_video_local

    excluir_video_local("arquivo-que-nao-existe.mp4")


@pytest.mark.unit
def test_varios_agendamentos_preservam_intervalo_minimo(banco_teste):
    import banco

    video_id = banco.registrar_video(
        url="https://youtube.com/watch?v=test", titulo="Teste", duracao_s=180
    )
    ids = [
        banco.registrar_corte(
            video_id=video_id,
            numero=i,
            corte_info={"tipo": "denso", "categoria": "podcast", "titulo": f"Corte {i}"},
            caminho_video=Path(f"corte-{i}.mp4"),
            caminho_txt=Path(f"corte-{i}.txt"),
        )
        for i in range(1, 4)
    ]
    base = datetime.now()
    conn = sqlite3.connect(banco_teste)
    for i, corte_id in enumerate(ids):
        conn.execute(
            "UPDATE cortes SET status='agendado', agendado_para=? WHERE id=?",
            ((base + timedelta(hours=i * 4)).strftime("%Y-%m-%d %H:%M:%S"), corte_id),
        )
    conn.commit()
    rows = conn.execute(
        "SELECT agendado_para FROM cortes WHERE status='agendado' ORDER BY agendado_para"
    ).fetchall()
    conn.close()

    datas = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in rows]
    assert all((b - a).total_seconds() >= 3 * 3600 for a, b in zip(datas, datas[1:]))
