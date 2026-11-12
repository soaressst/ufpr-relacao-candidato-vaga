import os
import csv
import sys
import time
import hashlib
from datetime import datetime, timezone

import requests

from pipeline.db import RAIZ

# Baixa as páginas oficiais de "relação candidato/vaga" por curso do Núcleo de Concursos da UFPR
# e guarda os arquivos INTOCADOS em data/raw/nc_ufpr/<ano>/, com um manifesto (url, data, hash).
# Não acessa o banco. Não baixa listas nominais de candidatos (dados pessoais).
#
# Catálogo montado em 29/10/2026 a partir do índice oficial
# https://servicos.nc.ufpr.br/PortalNC/VestibularesAnteriores e das páginas de cada edição.
# Edições sem tabela pública por curso encontrada: 2004, 2018 e 2021 em diante
# (para 2021+ o NC/UFPR só divulgou os cursos mais concorridos em notícias).
# Para 2021-2026 baixamos o quadro de VAGAS por curso (guia do candidato ou edital normativo),
# usado para completar as vagas que faltam na base da Liga.

ANTIGO = "http://www.nc.ufpr.br/concursos_institucionais/ufpr"
DOCUMENTO = "https://servicos.nc.ufpr.br/PortalNC/obterDocumento?pub="
CATALOGO = {
    2003: [f"{ANTIGO}/ps2003/inf_candvaga.htm"],
    2005: [f"{ANTIGO}/ps2005/cand_vaga_alfa.htm"],
    2006: [f"{ANTIGO}/ps2006/cand_vaga.htm"],
    2007: [f"{ANTIGO}/ps2007/cand_vaga.htm"],
    2008: [f"{ANTIGO}/ps2008/cand_vaga_c.htm"],
    2009: [f"{ANTIGO}/ps2009/cand_vaga_c.htm"],
    2010: [f"{ANTIGO}/ps2010/cand_vaga_c.htm"],
    2011: [f"{ANTIGO}/ps2011/cand_vaga_c.htm"],
    2012: [f"{ANTIGO}/ps2012/cand_vaga_c.htm"],
    2013: [f"{ANTIGO}/ps2013/candidato_vaga_ps2013.htm"],
    2014: [f"{ANTIGO}/ps2014/candidato_vaga_ps2014.htm"],
    2015: [f"{ANTIGO}/ps2015/candidato_vaga_ps2015.htm"],
    2016: [f"{ANTIGO}/ps2016/candvaga_curso.htm", f"{ANTIGO}/ps2016/documentos/candvaga_curso.pdf"],
    2017: [f"{ANTIGO}/ps2017/documentos/candvaga_curso.pdf"],
    2019: ["https://servicos.nc.ufpr.br/documentos/PS2019/cv/index.html"],
    2020: ["https://servicos.nc.ufpr.br/PortalNC/obterDocumento?pub=2401"],
}

# Quadro de vagas por curso: guia do candidato (2021-2024) ou Anexo II do edital normativo (2025-2026)
CATALOGO_VAGAS = {
    2021: [DOCUMENTO + "2556"],  # Guia do Candidato PS 2020/2021
    2022: [DOCUMENTO + "3364"],  # Guia do Candidato PS 2021/2022 (atualizado até 12/04/2022)
    2023: [DOCUMENTO + "4488"],  # Guia do Candidato PS 2023 (compilado com as retificações)
    2024: [DOCUMENTO + "6188"],  # Guia do Candidato PS 2024
    2025: [DOCUMENTO + "7659"],  # Edital n.º 25/2024-NC/PROGRAD
    2026: [DOCUMENTO + "8601"],  # Edital n.º 28/2025-NC/PROGRAP
    2027: [DOCUMENTO + "9363"],  # Edital n.º 50/2026-NC/PROGRAP (compilado com as retificações)
}
for _ano, _urls in CATALOGO_VAGAS.items():
    CATALOGO.setdefault(_ano, []).extend(_urls)

# Relatórios oficiais de ocupação das vagas do vestibular (https://servicos.nc.ufpr.br/PortalNC/RelatoriosEstatisticos):
# por curso e categoria, quantos foram aprovados só na chamada geral ("GERAL") e na geral + complementares
# ("FINAL"). Agregados por curso, sem nomes. O de 2023 só existe para a chamada geral.
RELATORIO = "https://servicos.nc.ufpr.br/PortalNC/AcessaRelatorios?processo=UFPR"
CATALOGO_OCUPACAO = {
    ano: [f"{RELATORIO}&ano={ano}&tipo=RESUMO%20CHAMADA%20GERAL"]
    + ([f"{RELATORIO}&ano={ano}&tipo=RESUMO%20FINAL"] if ano <= 2022 else [])
    for ano in range(2016, 2024)
}
for _ano, _urls in CATALOGO_OCUPACAO.items():
    CATALOGO.setdefault(_ano, []).extend(_urls)

PASTA = os.path.join(RAIZ, "data", "raw", "nc_ufpr")
MANIFESTO = os.path.join(PASTA, "manifesto.csv")
CABECALHO = {"User-Agent": "Mozilla/5.0 (projeto academico Liga Data Science UFPR)"}
PAUSA_SEGUNDOS = 2


def nome_arquivo(url, resposta):
    nome = url.rstrip("/").split("/")[-1].split("?")[0]
    if "obterDocumento" in url:
        nome = "documento_" + url.split("pub=")[-1]
    if "AcessaRelatorios" in url:
        nome = "ocupacao_final.html" if "RESUMO%20FINAL" in url else "ocupacao_chamada_geral.html"
    if "." not in nome:
        tipo = resposta.headers.get("Content-Type", "")
        nome += ".pdf" if "pdf" in tipo else ".html"
    return nome


def baixar(forcar=False):
    os.makedirs(PASTA, exist_ok=True)
    registros = []
    if os.path.exists(MANIFESTO):
        with open(MANIFESTO, encoding="utf-8") as f:
            registros = list(csv.DictReader(f))
    ja_baixados = {r["url"] for r in registros}

    for ano, urls in CATALOGO.items():
        for url in urls:
            if url in ja_baixados and not forcar:
                print(f"-> {ano}: já baixado ({url})")
                continue
            resposta = requests.get(url, headers=CABECALHO, timeout=60)
            resposta.raise_for_status()
            pasta_ano = os.path.join(PASTA, str(ano))
            os.makedirs(pasta_ano, exist_ok=True)
            arquivo = os.path.join(pasta_ano, nome_arquivo(url, resposta))
            with open(arquivo, "wb") as f:
                f.write(resposta.content)

            registros = [r for r in registros if r["url"] != url]
            registros.append({
                "ano": ano,
                "url": url,
                "arquivo": os.path.relpath(arquivo, RAIZ).replace("\\", "/"),
                "baixado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bytes": len(resposta.content),
                "sha256": hashlib.sha256(resposta.content).hexdigest(),
            })
            print(f"-> {ano}: {len(resposta.content)} bytes em {os.path.relpath(arquivo, RAIZ)}")
            time.sleep(PAUSA_SEGUNDOS)

    registros.sort(key=lambda r: (int(r["ano"]), r["url"]))
    with open(MANIFESTO, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=["ano", "url", "arquivo", "baixado_em", "bytes", "sha256"])
        escritor.writeheader()
        escritor.writerows(registros)


if __name__ == "__main__":
    print("--- Baixando relação candidato/vaga do NC-UFPR (camada raw) ---")
    baixar(forcar="--forcar" in sys.argv)
    print(f"\n--- CONCLUÍDO! Manifesto em {os.path.relpath(MANIFESTO, RAIZ)} ---")
