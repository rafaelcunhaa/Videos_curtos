import json

import banco


def test_extrair_watch():
    assert (
        banco.extrair_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_extrair_shorts():
    assert (
        banco.extrair_youtube_id("https://youtube.com/shorts/dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_extrair_embed():
    assert (
        banco.extrair_youtube_id("https://youtube.com/embed/dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_extrair_youtu_be():
    assert banco.extrair_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extrair_id_puro():
    assert banco.extrair_youtube_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_registrar_video(banco_teste):
    video_id = banco.registrar_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        titulo="Vídeo de teste",
        duracao_s=120.5,
        caminho_arquivo="teste.mp4",
    )

    videos = banco.listar_videos()

    assert len(videos) == 1

    video = videos[0]

    assert video["id"] == video_id
    assert video["youtube_id"] == "dQw4w9WgXcQ"
    assert video["titulo"] == "Vídeo de teste"
    assert video["duracao_s"] == 120.5


def test_registrar_video_atualiza_existente(banco_teste):
    banco.registrar_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        titulo="Primeiro título",
        duracao_s=100,
        caminho_arquivo="a.mp4",
    )

    banco.registrar_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        titulo="Título atualizado",
        duracao_s=250,
        caminho_arquivo="b.mp4",
    )

    videos = banco.listar_videos()

    assert len(videos) == 1
    assert videos[0]["titulo"] == "Título atualizado"
    assert videos[0]["duracao_s"] == 250


def test_resetar_video(banco_teste):
    banco.registrar_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        titulo="Teste",
        duracao_s=100,
        caminho_arquivo="teste.mp4",
    )

    banco.resetar_video("https://youtu.be/dQw4w9WgXcQ")

    videos = banco.listar_videos()

    assert videos[0]["num_cortes"] == 0


def test_registrar_corte(banco_teste):
    video_id = banco.registrar_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        titulo="Teste",
        duracao_s=100,
        caminho_arquivo="teste.mp4",
    )
    corte_id = banco.registrar_corte(
        video_id=video_id,
        numero=1,
        corte_info={
            "tipo": "historia",
            "categoria": "ia",
            "titulo": "Título do corte",
            "gancho": "Gancho incrível",
            "inicio": 10,
            "fim": 40,
        },
        caminho_video="output/video.mp4",
        caminho_txt="output/video.txt",
        desc_info={
            "titulo_yt": "Título YouTube",
            "descricao": "Descrição teste",
            "hashtags": ["#catolico", "#fé"],
        },
    )

    assert corte_id > 0

    cortes = banco.listar_cortes(video_id=video_id)

    assert len(cortes) == 1

    corte = cortes[0]

    assert corte["titulo"] == "Título do corte"
    assert corte["tipo"] == "historia"
    assert corte["categoria"] == "ia"
    assert corte["status"] == "pronto"
    assert corte["duracao_s"] == 30

    hashtags = json.loads(corte["hashtags"])

    assert hashtags == ["#catolico", "#fé"]

    videos = banco.listar_videos()

    assert videos[0]["num_cortes"] == 1


def test_atualizar_status_corte(banco_teste):
    video_id = banco.registrar_video(
        url="https://youtu.be/dQw4w9WgXcQ",
        titulo="Teste",
        duracao_s=100,
        caminho_arquivo="teste.mp4",
    )
    corte_id = banco.registrar_corte(
        video_id=video_id,
        numero=1,
        corte_info={
            "tipo": "historia",
            "categoria": "ia",
            "titulo": "Título do corte",
            "gancho": "Gancho incrível",
            "inicio": 10,
            "fim": 40,
        },
        caminho_video="output/video.mp4",
        caminho_txt="output/video.txt",
        desc_info={
            "titulo_yt": "Título YouTube",
            "descricao": "Descrição teste",
            "hashtags": ["#catolico", "#fé"],
        },
    )
