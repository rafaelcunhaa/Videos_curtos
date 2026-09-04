from pathlib import Path

import banco

banco.inicializar()

postados = banco.listar_cortes(status="postado")

apagados = 0
nao_encontrados = 0

for corte in postados:
    caminho = corte.get("caminho_video")

    if not caminho:
        continue

    arquivo = Path(caminho)

    if arquivo.exists():
        try:
            arquivo.unlink()
            print(f"✓ Apagado: {arquivo.name}")
            apagados += 1
        except Exception as e:
            print(f"✗ Erro ao apagar {arquivo.name}: {e}")
    else:
        nao_encontrados += 1

print()
print(f"Vídeos apagados: {apagados}")
print(f"Já inexistentes: {nao_encontrados}")
