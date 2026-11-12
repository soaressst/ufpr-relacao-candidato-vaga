"""Testa modelo hierárquico, ARIMAX e ajuste pelos inscritos do ano nos mesmos pares curso-ano.

- hierarquico: efeitos mistos no desvio do curso (intercepto e tendência por curso, encolhidos à média).
- hierarquico_grupos: o mesmo, com tendência fixa por área e por local.
- arimax_pop: ARIMA(0,1,1) com a população de 15 a 19 anos do Paraná como variável externa.
- comum_inscritos: nível comum + desvio, somando a variação do total de inscritos do ano previsto.
  Só existe 1 ano à frente: o total é divulgado antes do resultado por curso.

Rodar antes: python -W ignore -m analises.comparacao_arima
Uso: python -W ignore -m analises.comparacao_hierarquico
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from joblib import Parallel, delayed
from statsmodels.tsa.statespace.sarimax import SARIMAX

from analises import comparacao_modelos as cm
from analises.causas_baixa_procura import area
from analises.projecao_maioria_sobra import ARQUIVO_POP
from pipeline import modelo_previsao as mp
from pipeline.cursos import chave_curso

JANELA = 12  # anos usados no ajuste hierárquico
MIN_OBS = 6


def preparar(painel):
    chaves = {c: chave_curso(c) for c in painel["Curso_Ref"].unique()}
    p = painel.copy()
    p["area"] = p["Curso_Ref"].map(lambda c: area(chaves[c][0]))
    return p


def hierarquico_do_corte(painel, corte, indice, grupos):
    d = painel[(painel["Ano"] <= corte) & (painel["Ano"] > corte - JANELA)].copy()
    d["desvio"] = d["y"] - d["Ano"].map(indice)
    d["t"] = d["Ano"] - corte
    formula = "desvio ~ t * interior + t * C(area)" if grupos else "desvio ~ t"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = smf.mixedlm(formula, d, groups=d["Curso_Ref"], re_formula="~t").fit(reml=True, method="lbfgs")
    saida = {}
    fixos = d.drop_duplicates("Curso_Ref").set_index("Curso_Ref")
    for curso, efeito in m.random_effects.items():
        base = fixos.loc[[curso]]
        for h in cm.HORIZONTES:
            x = base.assign(t=h)
            fixo = float(m.predict(x).iloc[0])
            aleatorio = float(efeito.iloc[0] + efeito.iloc[1] * h)
            saida[(curso, corte, h)] = max(float(np.expm1(indice.iloc[-1] + fixo + aleatorio)), 0.0)
    return saida


def arimax(curso, corte, h_lista, anos, y, pop):
    if len(y) < MIN_OBS:
        p = np.full(3, y[-1])
    else:
        grade = pd.Series(y, index=anos).reindex(range(int(anos[0]), corte + 1))
        ex = np.log(pop.reindex(grade.index).values).reshape(-1, 1)
        fut = np.log(pop.reindex(range(corte + 1, corte + 4)).values).reshape(-1, 1)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = SARIMAX(grade.values, exog=ex, order=(0, 1, 1), trend="n").fit(disp=False, maxiter=50)
            p = np.asarray(r.forecast(3, exog=fut))
            if not np.isfinite(p).all() or np.abs(p - y[-1]).max() > 5:
                p = np.full(3, y[-1])
        except Exception:
            p = np.full(3, y[-1])
    return {(curso, corte, h): max(float(np.expm1(p[h - 1])), 0.0) for h in h_lista}


def elasticidade_inscritos(painel, corte, totais):
    """Quanto o nível comum anda para cada 1% de variação no total de inscritos, só com o passado."""
    indice = mp.indice_comum(painel[painel["Ano"] <= corte])
    comuns = indice.index.intersection(totais.index)
    a = indice.loc[comuns].diff().dropna()
    b = np.log(totais.loc[comuns]).diff().dropna()
    return float((a * b).sum() / (b * b).sum())


if __name__ == "__main__":
    base = pd.read_csv("analises/resultados_comparacao_arima.csv")
    painel = preparar(cm.carregar_painel())
    pop = pd.read_csv(ARQUIVO_POP).set_index("ano")["populacao_15a19"]
    hist = pd.read_csv(mp.ARQUIVO_HISTORICO)
    totais = hist.groupby("Ano")["Concorrentes"].sum()

    h1, h2 = {}, {}
    for corte in cm.CORTES:
        indice = mp.indice_comum(painel[painel["Ano"] <= corte])
        h1.update(hierarquico_do_corte(painel, corte, indice, False))
        h2.update(hierarquico_do_corte(painel, corte, indice, True))
    base["hierarquico"] = [h1.get(k, np.nan) for k in zip(base["curso"], base["corte"], base["h"])]
    base["hierarquico_grupos"] = [h2.get(k, np.nan) for k in zip(base["curso"], base["corte"], base["h"])]

    tarefas = []
    for (curso, corte), g in base.groupby(["curso", "corte"]):
        d = painel[(painel["Curso_Ref"] == curso) & (painel["Ano"] <= corte)]
        tarefas.append((curso, int(corte), list(g["h"]), d["Ano"].values, d["y"].values, pop))
    dic = {}
    for r in Parallel(n_jobs=-1)(delayed(arimax)(*t) for t in tarefas):
        dic.update(r)
    base["arimax_pop"] = [dic[k] for k in zip(base["curso"], base["corte"], base["h"])]

    # Nível comum + inscritos: desloca a previsão em log(1 + y) pela variação conhecida do total
    elas = {c: elasticidade_inscritos(painel, c, totais) for c in cm.CORTES}
    print("elasticidade do nível comum aos inscritos, por corte:", {c: round(v, 2) for c, v in elas.items()})
    ajuste = []
    for r in base.itertuples():
        alvo = r.corte + r.h
        if r.h == 1 and alvo in totais.index and r.corte in totais.index:
            ajuste.append(elas[r.corte] * np.log(totais[alvo] / totais[r.corte]))
        else:
            ajuste.append(0.0)
    base["comum_inscritos"] = np.expm1(np.log1p(base["comum_mais_desvio"]) + np.array(ajuste)).clip(lower=0)
    base.to_csv("analises/resultados_comparacao_hierarquico.csv", index=False)

    print("pares sem previsão hierárquica:", int(base["hierarquico"].isna().sum()))
    base["hierarquico"] = base["hierarquico"].fillna(base["repetir_ultimo"])
    base["hierarquico_grupos"] = base["hierarquico_grupos"].fillna(base["repetir_ultimo"])
    cm.METODOS = ["repetir_ultimo", "comum_mais_desvio", "comum_inscritos", "hierarquico", "hierarquico_grupos", "arimax_pop", "arima_011"]
    for h in cm.HORIZONTES:
        cm.resumo(base[base["h"] == h], f"{h} ano(s) à frente, todos os cortes")
    cm.resumo(base[(base["h"] == 1) & (base["corte"] >= 2020)], "1 ano à frente, cortes 2020-2025")
    cm.resumo(base[(base["h"] == 1) & (base["corte"] >= 2023)], "1 ano à frente, cortes 2023-2025")
    cm.resumo(base[(base["h"] == 1) & (base["repetir_ultimo"] < 3)], "1 ano à frente, abaixo de 3 candidatos por vaga")
