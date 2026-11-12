import os
import numpy as np
import pandas as pd
from statsmodels.tsa.api import Holt, SimpleExpSmoothing

from pipeline.db import RAIZ
from pipeline.cursos import mapear_historico

# Método padrão: nível comum + desvio do curso (previsão sem tendência), em log(1 + cand/vaga).
# A queda da procura é comum aos cursos e persiste; o desvio de cada curso tem mais ruído. Por isso a
# previsão usa o nível comum do último ano e suaviza só o desvio. Comparação em analises/03_modelos.md:
# empata com "repetir o último ano" no geral, ganha nos cursos abaixo de 3 candidatos por vaga e erra
# menos que a suavização por curso. Suavização simples e Holt seguem disponíveis em METODOS.
#
# Sobra de vagas: cand/vaga < 1 contra as VAGAS DE REFERÊNCIA (últimas vagas antes de 2025), porque
# desde 2025 o edital corta as vagas de cursos de baixa procura e cand/vaga do edital deixa de mostrar
# a sobra. Cand_Vaga_2026 também é contra a referência. Colunas extras no CSV: Vagas_Edital_2026,
# Vagas_Referencia e Vagas_Cortadas (vagas do edital abaixo da referência; só informativa).
#
# Incerteza: Faixa_2027_Min/Max é a faixa de 80% pelos erros reais do modelo 1 ano à frente
# (refeito a partir de 2017, 2020-2025); Prob_Sobra_2027 = parte desses erros que levaria cand/vaga < 1.
# Risco_2027 usa as faixas validadas com a ocupação oficial (<1, 1-1,5, 1,5-2, >=2).
# Testado e descartado: ajustar pelo total de inscritos do ano (erro 0,732 -> 0,734, sem ganho).
#
# Baseado no notebook "4. Script Python/01_modelo_concorrencia_ufpr.ipynb" (Holt), com correções:
#   - séries montadas pelo nome padronizado do curso (pipeline/cursos.py), não pelo texto exato
#   - 2019 removido junto com 2018 (2019 traz outra métrica: ~99 concorrentes por curso contra ~315 em 2020)
#   - linhas inválidas removidas (Vagas <= 0, Concorrentes_Efetivos < 0)
#   - curso só é previsto com pelo menos 3 anos válidos a partir de 2020 (como diz a metodologia)
#   - Ano_Minimo / Valor_Minimo calculados só no horizonte 2027-2032
# Não acessa o banco: lê e grava apenas CSVs em data/gold

ARQUIVO_HISTORICO = os.path.join(RAIZ, "data", "gold", "historico_candidato_vaga.csv")
ARQUIVO_PREVISAO = os.path.join(RAIZ, "data", "gold", "UFPR_Previsao_Concorrencia_Por_Curso_2027_2032.csv")
ANO_BASE = 2026
ANOS_FUTUROS = [2027, 2028, 2029, 2030, 2031, 2032]
MIN_ANOS_RECENTES = 3
METODO_PADRAO = "nivel_comum"
ALFA_DESVIO = 0.8  # escolhido só com anos anteriores em cada corte; estável em 0,8 desde 2017
ANO_CORTE_VAGAS = 2025  # primeiro edital com vagas cortadas até o nº de candidatos


def preparar_series(df):
    """Histórico válido por curso de 2026: uma linha por curso e ano com Cand_Vaga, Vagas,
    Vagas_Referencia e Vagas_Cortadas.

    `df` é o histórico de pipeline/consolidar_historico.py (Ano, Curso, Concorrentes, Vagas, ...).

    Desde 2025 o edital corta as vagas de cursos de baixa procura (em 2025, até o nº exato de
    candidatos), o que esconde a sobra. Por isso, de 2025 em diante a relação é calculada contra as
    VAGAS DE REFERÊNCIA: as últimas vagas do curso antes de 2025 (em geral as de 2024). Cursos que só
    existem a partir de 2025 usam as próprias vagas.
    """
    df = mapear_historico(df, ano_ref=ANO_BASE)
    df = df[df["Curso_Ref"].notna()]

    # Algumas edições têm o mesmo curso partido em duas linhas (uma só com vagas, outra só com
    # concorrentes): soma as duas e recalcula a relação (Concorrentes / Vagas)
    soma = df.groupby(["Curso_Ref", "Ano"], as_index=False)[["Vagas", "Concorrentes"]].sum(min_count=1)
    soma = soma[soma["Concorrentes"].notna() & soma["Vagas"].notna()].sort_values(["Curso_Ref", "Ano"])

    antes_do_corte = (soma["Ano"] < ANO_CORTE_VAGAS) & (soma["Vagas"] > 0)
    soma["Vagas_Referencia"] = soma["Vagas"].where(antes_do_corte).groupby(soma["Curso_Ref"]).ffill()
    depois = soma["Ano"] >= ANO_CORTE_VAGAS
    soma["Vagas_Cortadas"] = depois & (soma["Vagas"] < soma["Vagas_Referencia"])
    vagas_usadas = soma["Vagas"].where(~depois | soma["Vagas_Referencia"].isna(), soma["Vagas_Referencia"])

    soma = soma[(vagas_usadas > 0) & (soma["Concorrentes"] >= 0)].copy()
    soma["Cand_Vaga"] = soma["Concorrentes"] / vagas_usadas.loc[soma.index]
    return soma[["Curso_Ref", "Ano", "Cand_Vaga", "Vagas", "Vagas_Referencia", "Vagas_Cortadas"]]


METODOS = {
    "holt": lambda y: Holt(y, initialization_method="estimated"),
    "holt_amortecido": lambda y: Holt(y, damped_trend=True, initialization_method="estimated"),
    "suavizacao_simples": lambda y: SimpleExpSmoothing(y, initialization_method="estimated"),
}


def indice_comum(series):
    """Nível comum aos cursos: soma das variações medianas de log(1 + cand/vaga), ano a ano.
    Vem das variações (e não da mediana do ano) para que cursos novos não mudem o índice."""
    d = series.sort_values(["Curso_Ref", "Ano"])
    dif = np.log1p(d["Cand_Vaga"]).groupby(d["Curso_Ref"]).diff()
    return dif.groupby(d["Ano"]).median().fillna(0).cumsum()


def prever_nivel_comum(y_hist, anos_hist, indice):
    desvio = np.log1p(y_hist) - indice.reindex(anos_hist).values
    nivel = desvio[0]
    for v in desvio[1:]:
        nivel = ALFA_DESVIO * v + (1 - ALFA_DESVIO) * nivel
    return np.full(len(ANOS_FUTUROS), np.expm1(indice.iloc[-1] + nivel))


def prever(y_hist, anos_hist, metodo=METODO_PADRAO, indice=None):
    if metodo == "nivel_comum":
        return prever_nivel_comum(y_hist, anos_hist, indice)
    if metodo not in METODOS:
        raise ValueError(f"Método desconhecido: {metodo}")
    try:
        return METODOS[metodo](y_hist).fit(optimized=True).forecast(len(ANOS_FUTUROS))
    except Exception:
        # Fallback: tendência linear simples
        poly = np.polyfit(anos_hist, y_hist, 1)
        return np.polyval(poly, ANOS_FUTUROS)


HORIZONTE_MAX_CALIBRADO = 4  # erros de 5-6 anos à frente só existem cruzando a queda 2017->2021
CORTES_CALIBRACAO = [2017, 2020, 2021, 2022, 2023, 2024, 2025]


def calibrar_erros(series, metodo=METODO_PADRAO):
    """Erros reais do modelo (log de real/previsto) por horizonte, refazendo a previsão a partir de
    anos passados. Servem para a faixa de incerteza e a probabilidade de sobra."""
    erros = {h: [] for h in range(1, HORIZONTE_MAX_CALIBRADO + 1)}
    for corte in CORTES_CALIBRACAO:
        indice = indice_comum(series[series["Ano"] <= corte])
        for _, d in series.groupby("Curso_Ref"):
            treino, teste = d[d["Ano"] <= corte], d[d["Ano"] > corte]
            if len(treino) < 3 or teste.empty or treino["Ano"].iloc[-1] != corte:
                continue
            preds = prever(treino["Cand_Vaga"].values, treino["Ano"].values, metodo, indice)
            for ano, real in zip(teste["Ano"], teste["Cand_Vaga"]):
                h = ano - corte
                if h <= HORIZONTE_MAX_CALIBRADO and real > 0 and preds[h - 1] > 0:
                    erros[h].append(np.log(real / preds[h - 1]))
    return {h: np.array(e) for h, e in erros.items()}


def risco(valor):
    # Faixas validadas com a ocupação oficial 2016-2022 (analises/02_validacao_sobra.md)
    if valor < 1:
        return "Sobra certa"
    if valor < 1.5:
        return "Risco alto"
    if valor < 2:
        return "Atenção"
    return "Baixo"


def gerar_previsoes(df, metodo=METODO_PADRAO):
    series = preparar_series(df)
    erros = calibrar_erros(series, metodo)
    indice = indice_comum(series)
    campus_2026 = df[df["Ano"] == ANO_BASE].drop_duplicates("Curso").set_index("Curso")["Campus"]
    resultados = []

    for curso, df_c in series.groupby("Curso_Ref", sort=False):
        y_hist = df_c["Cand_Vaga"].values
        anos_hist = df_c["Ano"].values

        # Precisa do valor de 2026 e de pelo menos 3 anos válidos desde 2020
        if anos_hist[-1] != ANO_BASE or (anos_hist >= 2020).sum() < MIN_ANOS_RECENTES:
            continue

        # Projeção bounded: a concorrência não pode ser negativa
        preds = [max(0.0, float(v)) for v in prever(y_hist, anos_hist, metodo, indice)]

        # Pontos críticos: piso no horizonte 2027-2032 e primeiro ano (desde o 1.º edital com cortes)
        # com cand/vaga < 1, sempre contra as vagas de referência
        i_min = int(np.argmin(preds))
        observados = df_c[df_c["Ano"] >= ANO_CORTE_VAGAS]
        anos_sobra = [a for a, v in zip(observados["Ano"], observados["Cand_Vaga"]) if v < 1.0]
        anos_sobra += [a for a, v in zip(ANOS_FUTUROS, preds) if v < 1.0]
        ultimo = df_c.iloc[-1]

        # Faixa de 80% e probabilidade de sobra em 2027, pelos erros reais do modelo 1 ano à frente
        e1 = erros[1]
        prev_2027 = preds[0]
        faixa = (prev_2027 * np.exp(np.quantile(e1, 0.1)), prev_2027 * np.exp(np.quantile(e1, 0.9))) if prev_2027 > 0 else (0.0, 0.0)
        prob_sobra = float(np.mean(prev_2027 * np.exp(e1) < 1.0)) if prev_2027 > 0 else 1.0

        resultados.append({
            "Curso": curso,
            "Campus": campus_2026.get(curso),
            "Cand_Vaga_2026": round(float(y_hist[-1]), 2),
            "Ano_Minimo": ANOS_FUTUROS[i_min],
            "Valor_Minimo": round(preds[i_min], 2),
            "Ano_Entrada_Sobra_Vagas": int(anos_sobra[0]) if anos_sobra else "Sem Sobra",
            "Vagas_Edital_2026": int(ultimo["Vagas"]),
            "Vagas_Referencia": int(ultimo["Vagas_Referencia"]) if pd.notna(ultimo["Vagas_Referencia"]) else None,
            "Vagas_Cortadas": bool(observados["Vagas_Cortadas"].any()),
            "Prev_2027": round(prev_2027, 2),
            "Faixa_2027_Min": round(faixa[0], 2),
            "Faixa_2027_Max": round(faixa[1], 2),
            "Prob_Sobra_2027": round(prob_sobra, 2),
            "Risco_2027": risco(prev_2027),
        })

    return pd.DataFrame(resultados).sort_values("Curso").reset_index(drop=True)


if __name__ == "__main__":
    print("--- 1. Lendo histórico consolidado (camada gold) ---")
    df_hist = pd.read_csv(ARQUIVO_HISTORICO)
    print(f"-> {len(df_hist)} linhas entre {df_hist['Ano'].min()} e {df_hist['Ano'].max()}.")

    print(f"--- 2. Ajustando modelo por curso ({METODO_PADRAO}) ---")
    df_previsoes = gerar_previsoes(df_hist)
    print(f"-> Previsões geradas para {len(df_previsoes)} cursos.")

    df_previsoes.to_csv(ARQUIVO_PREVISAO, index=False)
    print(f"-> Arquivo gravado em {os.path.relpath(ARQUIVO_PREVISAO, RAIZ)}")
    print("\n--- MODELO CONCLUÍDO! (para carregar no banco: python -m pipeline.etl_ingestao) ---")
