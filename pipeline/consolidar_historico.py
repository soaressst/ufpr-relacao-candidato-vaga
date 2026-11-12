import os
import re
import pandas as pd

from pipeline.db import RAIZ
from pipeline.cursos import chave_curso

# Monta o histórico de candidato/vaga por curso que alimenta o modelo (data/gold/historico_candidato_vaga.csv):
#   2003, 2005-2017 e 2020: raspagem oficial do NC-UFPR (data/silver/nc_candidato_vaga.csv)
#   2021-2026: candidatos e treineiros da base consolidada pela Liga
#              (data/gold/UFPR_Vestibular_Consolidado_Gold.csv); os totais de inscritos batem com os
#              divulgados pela UFPR. As VAGAS vêm do quadro oficial de cada guia/edital
#              (data/silver/nc_vagas_por_curso.csv); só onde não há par oficial fica a vaga da base.
# Fora: 2004 e 2018 (sem tabela pública encontrada) e 2019 (o NC só publicou os convocados para a 2.ª fase).
#
# A relação é Concorrentes / Vagas, como publica o NC: os treineiros já NÃO estão nos concorrentes
# ("T - Treineiros inscritos (não contabilizados na relação candidato/vaga)"), então não são descontados.

ARQUIVO_NC = os.path.join(RAIZ, "data", "silver", "nc_candidato_vaga.csv")
ARQUIVO_VAGAS = os.path.join(RAIZ, "data", "silver", "nc_vagas_por_curso.csv")
ARQUIVO_LIGA = os.path.join(RAIZ, "data", "gold", "UFPR_Vestibular_Consolidado_Gold.csv")
ARQUIVO_SAIDA = os.path.join(RAIZ, "data", "gold", "historico_candidato_vaga.csv")
PRIMEIRO_ANO_LIGA = 2021


def _sem_abi(chave):
    # ABI (área básica de ingresso): em 2026 a base pôs os candidatos no nome comum
    # ("Ciências Biológicas - Bacharelado") e as vagas no nome ABI ("Ciências Biológicas ABI (Bacharelado)")
    return (re.sub(r"\s*abi$", "", chave[0] or ""),) + tuple(chave[1:])


def vagas_oficiais(liga):
    """Para cada linha da base (2021+), a vaga oficial do quadro do mesmo ano, ou None.

    Liga pela chave completa (nome, grau, cidade, turno); se não achar, pela chave sem "ABI";
    por último, sem "ABI" e sem grau, só quando há um único curso possível dos dois lados.
    """
    quadro = pd.read_csv(ARQUIVO_VAGAS)
    quadro["chave"] = quadro["curso"].map(chave_curso)
    resultado = pd.Series(index=liga.index, dtype="float")
    for ano, base in liga.groupby("Ano"):
        q = quadro[quadro["ano"] == ano]
        chaves_base = base["Curso"].map(chave_curso)
        niveis = [
            lambda k: k,
            _sem_abi,
            lambda k: (_sem_abi(k)[0],) + tuple(k[2:]),
        ]
        for nivel in niveis:
            faltam = resultado.loc[base.index].isna()
            if not faltam.any():
                break
            k_quadro = q["chave"].map(nivel)
            contagem = k_quadro.value_counts()
            mapa = {k: v for k, v in zip(k_quadro, q["vagas"]) if contagem[k] == 1}
            k_base = chaves_base[faltam].map(nivel)
            unicos = k_base.map(k_base.value_counts()) == 1
            resultado.loc[k_base[unicos].index] = k_base[unicos].map(mapa)
    return resultado


def juntar_linhas_partidas(liga):
    """Na base, alguns cursos aparecem em duas linhas no mesmo ano (uma com candidatos, outra com
    vagas, com nomes um pouco diferentes, ex.: "... - - Tecnológico"). Junta pela chave padronizada,
    somando os números e ficando com o nome da linha que tem candidatos."""
    liga = liga.copy()
    liga["_chave"] = liga["Curso"].map(chave_curso)
    liga["_tem_cand"] = liga["Concorrentes"].notna()
    liga = liga.sort_values(["Ano", "_chave", "_tem_cand"], ascending=[True, True, False])
    juntas = liga.groupby(["Ano", "_chave"], as_index=False, sort=False).agg(
        Curso=("Curso", "first"),
        Campus=("Campus", "first"),
        Concorrentes=("Concorrentes", lambda s: s.sum(min_count=1)),
        Treineiros=("Treineiros", lambda s: s.sum(min_count=1)),
        Vagas=("Vagas", lambda s: s.sum(min_count=1)),
        Flag_Outlier_Fonte=("Flag_Outlier_Fonte", "any"),
    )
    return juntas.drop(columns="_chave")


def consolidar():
    nc = pd.read_csv(ARQUIVO_NC).rename(columns={
        "ano": "Ano", "curso": "Curso", "concorrentes": "Concorrentes",
        "treineiros": "Treineiros", "vagas": "Vagas",
    })
    nc["Campus"] = nc["Curso"].map(lambda c: chave_curso(c)[2])
    nc["Fonte"] = "NC-UFPR (raspagem oficial)"

    # As linhas marcadas como outlier na base tinham vagas lidas errado do guia de 2021
    # (notas de rodapé grudadas: "40²⁶" virou 4026); com a vaga oficial elas voltam a valer
    liga = pd.read_csv(ARQUIVO_LIGA)
    liga = liga[(liga["Ano"] >= PRIMEIRO_ANO_LIGA) & liga["Curso"].notna()].copy()
    liga = juntar_linhas_partidas(liga)
    oficial = vagas_oficiais(liga)
    liga["Fonte"] = "Base da Liga (candidatos) + vagas do quadro oficial"
    sem_par = oficial.isna()
    liga.loc[sem_par, "Fonte"] = "Base da Liga (candidatos e vagas)"
    liga.loc[sem_par & liga["Flag_Outlier_Fonte"], "Vagas"] = None
    liga["Vagas"] = oficial.where(~sem_par, liga["Vagas"])

    colunas = ["Ano", "Curso", "Campus", "Concorrentes", "Treineiros", "Vagas", "Fonte"]
    df = pd.concat([nc[colunas], liga[colunas]], ignore_index=True)
    df["Cand_Vaga"] = (df["Concorrentes"] / df["Vagas"]).where(df["Vagas"] > 0).round(4)
    # A partir de 2025 o edital publicado mostra as vagas de cursos de baixa procura cortadas até o
    # número de candidatos (ex.: Eng. de Aquicultura/Palotina: 48 vagas até 2024, 5 em 2025 com 5
    # candidatos). Nesses casos cand/vaga = 1 por construção e não mede a sobra de vagas.
    df["Vagas_Ajustadas_Demanda"] = (df["Ano"] >= 2025) & (df["Concorrentes"] == df["Vagas"])
    return df.sort_values(["Ano", "Curso"]).reset_index(drop=True)


if __name__ == "__main__":
    print("--- Consolidando histórico de candidato/vaga ---")
    df = consolidar()
    df.to_csv(ARQUIVO_SAIDA, index=False)
    print(df.groupby("Fonte")["Ano"].agg(["min", "max", "count"]).to_string())
    print(f"\n--- {len(df)} linhas gravadas em {os.path.relpath(ARQUIVO_SAIDA, RAIZ)} ---")
