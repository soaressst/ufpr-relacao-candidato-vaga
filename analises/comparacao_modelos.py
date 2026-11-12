"""Compara modelos de previsão de candidatos por vaga com um teste em anos passados.

Para cada ano de corte, cada método só enxerga dados até aquele ano e prevê os anos seguintes.
Todos os métodos são avaliados nos mesmos pares curso-ano, e "repetir o último ano" é a referência.
O erro é comparado com bootstrap por curso (o mesmo curso em vários anos não é independente).

Uso: python -W ignore -m analises.comparacao_modelos
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.api import Holt, SimpleExpSmoothing

from pipeline import modelo_previsao as mp
from pipeline.cursos import chave_curso

CORTES = [2012, 2013, 2014, 2015, 2016, 2017, 2020, 2021, 2022, 2023, 2024, 2025]
HORIZONTES = [1, 2, 3]
GRADE_ALFA = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
GRADE_ALFA_COMUM = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
COLUNAS = ["y", "media3", "media_longa", "desvio", "n_obs", "interior", "noturno", "licenciatura", "tecnologico"]


def carregar_painel():
    s = mp.preparar_series(pd.read_csv(mp.ARQUIVO_HISTORICO)).copy()
    s["y"] = np.log1p(s["Cand_Vaga"])
    chaves = {c: chave_curso(c) for c in s["Curso_Ref"].unique()}
    s["interior"] = s["Curso_Ref"].map(lambda c: chaves[c][2] != "Curitiba").astype(int)
    s["noturno"] = s["Curso_Ref"].map(lambda c: chaves[c][3] == "N").astype(int)
    s["licenciatura"] = s["Curso_Ref"].map(lambda c: chaves[c][1] == "Licenciatura").astype(int)
    s["tecnologico"] = s["Curso_Ref"].map(lambda c: chaves[c][1] == "Tecnológico").astype(int)
    return s.sort_values(["Curso_Ref", "Ano"]).reset_index(drop=True)


def _features(d):
    """Características de um curso usando só as linhas de `d` (ordem por ano, última = origem)."""
    y = d["y"].values
    ultimo = d.iloc[-1]
    return {"y": y[-1], "media3": y[-3:].mean(), "media_longa": y.mean(),
            "desvio": y[-5:].std() if len(y) > 1 else 0.0, "n_obs": min(len(y), 15),
            "interior": ultimo["interior"], "noturno": ultimo["noturno"],
            "licenciatura": ultimo["licenciatura"], "tecnologico": ultimo["tecnologico"]}


def base_treino(painel, corte, h):
    """Pares (origem, alvo) com alvo = origem + h e alvo <= corte: nada do futuro entra no treino."""
    linhas = []
    for _, d in painel[painel["Ano"] <= corte].groupby("Curso_Ref"):
        por_ano = dict(zip(d["Ano"], d["y"]))
        for i in range(len(d)):
            ano = d["Ano"].iloc[i]
            if ano + h in por_ano and i >= 1:
                linhas.append({**_features(d.iloc[: i + 1]), "alvo": por_ano[ano + h]})
    return pd.DataFrame(linhas)


def suavizar(y, alfa):
    nivel = y[0]
    for v in y[1:]:
        nivel = alfa * v + (1 - alfa) * nivel
    return nivel


def melhor_alfa(painel, corte):
    """Escolhe um alfa único para todos os cursos, só com os cortes anteriores a `corte`."""
    erros = {a: [] for a in GRADE_ALFA}
    for c in [x for x in CORTES if x < corte]:
        for _, d in painel[painel["Ano"] <= c + 1].groupby("Curso_Ref"):
            treino, alvo = d[d["Ano"] <= c], d[d["Ano"] == c + 1]
            if len(treino) < 3 or alvo.empty or treino["Ano"].iloc[-1] != c:
                continue
            for a in GRADE_ALFA:
                erros[a].append(abs(suavizar(treino["y"].values, a) - alvo["y"].iloc[0]))
    medias = {a: np.mean(e) for a, e in erros.items() if e}
    return min(medias, key=medias.get) if medias else 0.5


def indice_comum(painel, corte):
    return mp.indice_comum(painel[painel["Ano"] <= corte])


def comum_mais_desvio(hist, indice, alfa):
    """Previsão = nível comum do último ano + desvio do curso suavizado."""
    desvio = hist["y"].values - hist["Ano"].map(indice).values
    return indice.iloc[-1] + suavizar(desvio, alfa)


def melhor_alfa_comum(painel, corte):
    """Como melhor_alfa, para o modelo de nível comum: só usa cortes anteriores a `corte`."""
    erros = {a: [] for a in GRADE_ALFA_COMUM}
    for c in [x for x in CORTES if x < corte]:
        indice = indice_comum(painel, c)
        for _, d in painel[painel["Ano"] <= c + 1].groupby("Curso_Ref"):
            treino, alvo = d[d["Ano"] <= c], d[d["Ano"] == c + 1]
            if len(treino) < 3 or alvo.empty or treino["Ano"].iloc[-1] != c:
                continue
            for a in GRADE_ALFA_COMUM:
                erros[a].append(abs(comum_mais_desvio(treino, indice, a) - alvo["y"].iloc[0]))
    medias = {a: np.mean(e) for a, e in erros.items() if e}
    return min(medias, key=medias.get) if medias else 0.5


def _ajuste_serie(modelo, cand_vaga, h):
    try:
        return max(float(modelo(cand_vaga).fit(optimized=True).forecast(h)[-1]), 0.0)
    except Exception:
        return float(cand_vaga[-1])


def previsoes_do_corte(painel, corte):
    alfa = melhor_alfa(painel, corte)
    alfa_comum = melhor_alfa_comum(painel, corte)
    indice = indice_comum(painel, corte)
    linhas = []
    for h in HORIZONTES:
        treino = base_treino(painel, corte, h)
        if len(treino) < 100:
            continue
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(treino[COLUNAS], treino["alvo"])
        arvores = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150,
                                                min_samples_leaf=20, random_state=0)
        arvores.fit(treino[COLUNAS], treino["alvo"])
        for curso, d in painel.groupby("Curso_Ref"):
            hist = d[d["Ano"] <= corte]
            alvo = d[d["Ano"] == corte + h]
            if len(hist) < 3 or alvo.empty or hist["Ano"].iloc[-1] != corte:
                continue
            x = pd.DataFrame([_features(hist)])[COLUNAS]
            cv = hist["Cand_Vaga"].values
            r, a = float(ridge.predict(x)[0]), float(arvores.predict(x)[0])
            s = suavizar(hist["y"].values, alfa)
            ingenuo = float(np.expm1(hist["y"].iloc[-1]))
            linhas.append({
                "curso": curso, "corte": corte, "h": h, "real": alvo["Cand_Vaga"].iloc[0],
                "repetir_ultimo": ingenuo,
                "media_3_anos": float(np.expm1(hist["y"].iloc[-3:].mean())),
                "ses_por_curso": _ajuste_serie(lambda v: SimpleExpSmoothing(v, initialization_method="estimated"), cv, h),
                "holt_amortecido": _ajuste_serie(lambda v: Holt(v, damped_trend=True, initialization_method="estimated"), cv, h),
                "ses_alfa_unico": float(np.expm1(s)),
                "ridge_painel": max(float(np.expm1(r)), 0.0),
                "arvores_painel": max(float(np.expm1(a)), 0.0),
                "combinacao": float(np.expm1((r + s) / 2)),
                "comum_mais_desvio": max(float(np.expm1(comum_mais_desvio(hist, indice, alfa_comum))), 0.0),
            })
    return linhas


METODOS = ["repetir_ultimo", "media_3_anos", "ses_por_curso", "holt_amortecido", "ses_alfa_unico",
           "ridge_painel", "arvores_painel", "combinacao", "comum_mais_desvio"]


def bootstrap_vs_ref(d, metodo, n=2000, seed=0):
    """Diferença de erro absoluto (método - repetir o último ano), reamostrando cursos."""
    dif = (d[metodo] - d["real"]).abs() - (d["repetir_ultimo"] - d["real"]).abs()
    por_curso = dif.groupby(d["curso"]).agg(["sum", "count"]).values
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(por_curso), (n, len(por_curso)))
    medias = por_curso[idx, 0].sum(1) / por_curso[idx, 1].sum(1)
    return dif.mean(), np.percentile(medias, 2.5), np.percentile(medias, 97.5)


def resumo(d, rotulo):
    print(f"\n=== {rotulo}: {len(d)} pares, {d['curso'].nunique()} cursos ===")
    print(f"{'método':18} {'erro':>6} {'log':>6} {'dif':>7} {'IC 95% da dif':>18} {'pega<1':>7} {'acerta<1':>8}")
    real_sobra = d["real"] < 1
    for m in METODOS:
        erro = (d[m] - d["real"]).abs().mean()
        erro_log = (np.log1p(d[m]) - np.log1p(d["real"])).abs().mean()
        dif, lo, hi = bootstrap_vs_ref(d, m)
        pred = d[m] < 1
        recall = (pred & real_sobra).sum() / max(real_sobra.sum(), 1)
        prec = (pred & real_sobra).sum() / max(pred.sum(), 1)
        print(f"{m:18} {erro:6.3f} {erro_log:6.3f} {dif:7.3f} [{lo:7.3f},{hi:7.3f}] {recall:7.0%} {prec:8.0%}")


if __name__ == "__main__":
    painel = carregar_painel()
    print("alfa único escolhido para cada corte:", {c: melhor_alfa(painel, c) for c in CORTES})
    print("alfa do modelo de nível comum:", {c: melhor_alfa_comum(painel, c) for c in CORTES})
    linhas = []
    for corte in CORTES:
        linhas += previsoes_do_corte(painel, corte)
    r = pd.DataFrame(linhas)
    r.to_csv("analises/resultados_comparacao_modelos.csv", index=False)
    for h in HORIZONTES:
        resumo(r[r["h"] == h], f"{h} ano(s) à frente, todos os cortes")
    resumo(r[(r["h"] == 1) & (r["corte"] >= 2020)], "1 ano à frente, cortes 2020-2025")
    resumo(r[(r["h"] == 1) & (r["corte"] >= 2023)], "1 ano à frente, cortes 2023-2025")
    resumo(r[(r["h"] == 1) & (r["repetir_ultimo"] < 3)], "1 ano à frente, cursos abaixo de 3 candidatos por vaga")
