"""Testa a família ARIMA nos mesmos pares curso-ano de analises/comparacao_modelos.py.

Série anual em log(1 + cand/vaga), com os anos sem dado (2004, 2018, 2019) como faltantes, que o
filtro de Kalman do SARIMAX trata sem inventar valor. Ajuste por curso e por corte, só com o passado.
Com menos de MIN_OBS anos, ou se o ajuste falhar, o método repete o último ano e isso é contado.

Rodar antes: python -W ignore -m analises.comparacao_modelos
Uso: python -W ignore -m analises.comparacao_arima
"""
import warnings

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from statsmodels.tsa.forecasting.theta import ThetaModel
from statsmodels.tsa.statespace.sarimax import SARIMAX

from analises import comparacao_modelos as cm
from pipeline import modelo_previsao as mp

MIN_OBS = 6
GRADE_AUTO = [(0, 1, 0), (0, 1, 1), (1, 1, 0), (1, 1, 1), (1, 0, 0), (0, 0, 1), (1, 0, 1)]
FIXOS = {"arima_011": (0, 1, 1), "arima_110": (1, 1, 0), "arima_111": (1, 1, 1), "arima_100": (1, 0, 0)}


def _anual(anos, valores):
    return pd.Series(valores, index=anos).reindex(range(int(anos[0]), int(anos[-1]) + 1)).values


def _ajustar(y, ordem, tendencia=None):
    tendencia = tendencia if tendencia is not None else ("c" if ordem[1] == 0 else "n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return SARIMAX(y, order=ordem, trend=tendencia).fit(disp=False, maxiter=50)


def _prever(y, ordem, tendencia=None):
    return _ajustar(y, ordem, tendencia).forecast(3)


def _auto(y):
    """Escolhe a ordem pelo AICc, curso a curso."""
    melhor, melhor_aicc = None, np.inf
    n = int(np.isfinite(y).sum())
    for ordem in GRADE_AUTO:
        try:
            r = _ajustar(y, ordem)
        except Exception:
            continue
        k = len(r.params)
        if n - k - 1 <= 0 or not np.isfinite(r.aic):
            continue
        aicc = r.aic + 2 * k * (k + 1) / (n - k - 1)
        if aicc < melhor_aicc:
            melhor, melhor_aicc = r, aicc
    if melhor is None:
        raise ValueError("nenhuma ordem ajustou")
    return melhor.forecast(3)


def previsoes_de_um_curso(curso, hist, corte, indice):
    anos, y = hist["Ano"].values, hist["y"].values
    ultimo = y[-1]
    saida, falhas = {}, {}

    def tentar(nome, f):
        try:
            p = np.asarray(f(), dtype=float)
            if not np.isfinite(p).all() or np.abs(p - ultimo).max() > 5:
                raise ValueError("previsão explosiva")
            saida[nome], falhas[nome] = p, 0
        except Exception:
            saida[nome], falhas[nome] = np.full(3, ultimo), 1

    serie = _anual(anos, y)
    longa = len(y) >= MIN_OBS
    desvio = _anual(anos, y - indice.reindex(anos).values)

    def so_longa(f):
        if not longa:
            raise ValueError("série curta")
        return f()

    for nome, ordem in FIXOS.items():
        tentar(nome, lambda o=ordem: so_longa(lambda: _prever(serie, o)))
    tentar("arima_010_drift", lambda: so_longa(lambda: _prever(serie, (0, 1, 0), "c")))
    tentar("auto_arima", lambda: so_longa(lambda: _auto(serie)))
    tentar("theta", lambda: so_longa(lambda: ThetaModel(y, period=1, deseasonalize=False).fit().forecast(3).values))
    # Mesma ideia do nível comum: ARIMA só no desvio do curso, somando o nível comum do último ano
    tentar("comum_arima_011", lambda: so_longa(lambda: _prever(desvio, (0, 1, 1)) + indice.iloc[-1]))
    tentar("comum_arima_100", lambda: so_longa(lambda: _prever(desvio, (1, 0, 0)) + indice.iloc[-1]))

    linhas = []
    for h in cm.HORIZONTES:
        linha = {"curso": curso, "corte": corte, "h": h}
        for nome, p in saida.items():
            linha[nome] = max(float(np.expm1(p[h - 1])), 0.0)
            linha["falha_" + nome] = falhas[nome]
        linha["n_obs"] = len(y)
        linhas.append(linha)
    return linhas


def tarefas(painel, pares):
    for corte in sorted(pares["corte"].unique()):
        indice = mp.indice_comum(painel[painel["Ano"] <= corte])
        cursos = pares.loc[pares["corte"] == corte, "curso"].unique()
        for curso in cursos:
            d = painel[(painel["Curso_Ref"] == curso) & (painel["Ano"] <= corte)]
            yield curso, d[["Ano", "y"]].copy(), corte, indice


NOVOS = list(FIXOS) + ["arima_010_drift", "auto_arima", "theta", "comum_arima_011", "comum_arima_100"]

if __name__ == "__main__":
    base = pd.read_csv("analises/resultados_comparacao_modelos.csv")
    painel = cm.carregar_painel()
    res = Parallel(n_jobs=-1)(delayed(previsoes_de_um_curso)(*t) for t in tarefas(painel, base))
    novo = pd.DataFrame([x for lista in res for x in lista])
    r = base.merge(novo, on=["curso", "corte", "h"], how="inner", validate="one_to_one")
    assert len(r) == len(base), "os pares têm de ser os mesmos da comparação principal"
    r.to_csv("analises/resultados_comparacao_arima.csv", index=False)

    print("% de pares em que o método caiu em 'repetir o último ano' (série curta ou falha):")
    print({m: round(r.loc[r["h"] == 1, "falha_" + m].mean(), 3) for m in NOVOS})
    cm.METODOS = ["repetir_ultimo", "ses_por_curso", "comum_mais_desvio"] + NOVOS
    for h in cm.HORIZONTES:
        cm.resumo(r[r["h"] == h], f"{h} ano(s) à frente, todos os cortes")
    cm.resumo(r[(r["h"] == 1) & (r["corte"] >= 2020)], "1 ano à frente, cortes 2020-2025")
    cm.resumo(r[(r["h"] == 1) & (r["corte"] >= 2023)], "1 ano à frente, cortes 2023-2025")
    cm.resumo(r[(r["h"] == 1) & (r["repetir_ultimo"] < 3)], "1 ano à frente, abaixo de 3 candidatos por vaga")
    # Comparação justa: só onde o ARIMA de fato ajustou um modelo
    cm.resumo(r[(r["h"] == 1) & (r["n_obs"] >= MIN_OBS)], f"1 ano à frente, cursos com {MIN_OBS}+ anos de dados")
    cm.resumo(r[(r["h"] == 1) & (r["n_obs"] >= 12)], "1 ano à frente, cursos com 12+ anos de dados")
