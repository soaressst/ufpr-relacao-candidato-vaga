"""Em que ano 50% + 1 dos cursos teriam mais vagas do que candidatos?

Simula cada curso por modelo de nível local em log: nível(t+1) = nível(t) + choque do ano + ruído do
curso, e valor observado = nível + ruído do ano. O choque do ano é comum a todos e sai do histórico;
a tendência média é o que muda entre os cenários. As vagas ficam nas vagas de referência.
É uma projeção condicional aos cenários, não uma previsão de um ano exato.

Uso: python -W ignore -m analises.projecao_maioria_sobra
"""
import os

import matplotlib
import numpy as np
import pandas as pd

from pipeline import modelo_previsao as mp
from pipeline.db import RAIZ

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ARQUIVO_POP = os.path.join(RAIZ, "data", "ref", "ibge_populacao_15a19_parana.csv")
PASTA_FIG = os.path.join(RAIZ, "analises", "figuras")
ANO_INICIO, ANO_FIM = 2026, 2060
N_SIM = 5000
PISO = 0.02  # cand/vaga 0 não tem log
ALFA = mp.ALFA_DESVIO


def carregar():
    s = mp.preparar_series(pd.read_csv(mp.ARQUIVO_HISTORICO)).copy()
    s["y"] = np.log(s["Cand_Vaga"].clip(lower=PISO))
    s = s.sort_values(["Curso_Ref", "Ano"])
    s["dy"] = s.groupby("Curso_Ref")["y"].diff()
    s["gap"] = s.groupby("Curso_Ref")["Ano"].diff()
    return s


def choques_anuais(s, ate=ANO_INICIO):
    """Variação mediana por ano entre cursos, em log, dividida pelos anos sem dado (ex.: 2017->2020)."""
    d = s[s["dy"].notna() & (s["Ano"] <= ate)]
    g = d.groupby("Ano").agg(mediana=("dy", "median"), gap=("gap", "median"), n=("dy", "size"))
    g["por_ano"] = g["mediana"] / g["gap"]
    return g


def variancias(s, g):
    """Separa o ruído de um ano (que se desfaz) do que muda de vez no curso, pela autocovariância."""
    # Só cursos perto do limite: decidem quem cruza 1, e nos cursos minúsculos o log explode o ruído
    d = s[(s["gap"] == 1) & s["Cand_Vaga"].between(0.5, 4)].copy()
    d["res"] = d["dy"] - d["Ano"].map(g["mediana"])
    d["res_ant"] = d.groupby("Curso_Ref")["res"].shift()
    d = d[d["res_ant"].notna() & (d.groupby("Curso_Ref")["Ano"].diff() == 1)]
    var, cov = d["res"].var(), (d["res"] * d["res_ant"]).mean()
    ruido = max(-cov, 0.0)
    return np.sqrt(ruido), np.sqrt(max(var - 2 * ruido, 0.0))


def niveis(s, ano=ANO_INICIO, minimo=1):
    """Nível atual por curso, como no modelo: nível comum do ano + desvio do curso suavizado."""
    atual = s[s["Ano"] <= ano]
    indice = atual.groupby("Ano")["dy"].median().fillna(0).cumsum()
    n = {}
    for curso, d in atual.groupby("Curso_Ref"):
        if d["Ano"].iloc[-1] != ano or len(d) < minimo:
            continue
        desvio = d["y"].values - indice.reindex(d["Ano"]).values
        nivel = desvio[0]
        for v in desvio[1:]:
            nivel = ALFA * v + (1 - ALFA) * nivel
        n[curso] = indice.iloc[-1] + nivel
    return pd.Series(n)


def simular(l0, tendencia, g_hist, sig_ruido, sig_nivel, anos, incerteza=0.0, seed=1):
    """`tendencia`: array por ano (log por ano). Devolve % abaixo de 1 por simulação e ano."""
    rng = np.random.default_rng(seed)
    choques = g_hist - g_hist.mean()
    nivel = np.tile(l0.values, (N_SIM, 1))
    desvio = rng.normal(0, incerteza, N_SIM)[:, None] if incerteza else 0.0
    parte = np.zeros((N_SIM, len(anos)))
    for i in range(len(anos)):
        choque = rng.choice(choques, N_SIM)[:, None]
        nivel = nivel + tendencia[i] + desvio + choque + rng.normal(0, sig_nivel, nivel.shape)
        obs = nivel + rng.normal(0, sig_ruido, nivel.shape)
        parte[:, i] = (obs < 0).mean(1)
    return parte


def tabela_cenarios(parte, anos, n_cursos):
    limite = (n_cursos // 2 + 1) / n_cursos
    cruzou = parte >= limite
    primeiro = np.where(cruzou.any(1), np.array(anos)[cruzou.argmax(1)], 9999)
    q = lambda p: np.percentile(primeiro, p)  # noqa: E731
    texto = lambda v: "depois de 2060" if v == 9999 else str(int(v))  # noqa: E731
    return {"mediana": texto(q(50)), "faixa_80": f"{texto(q(10))} a {texto(q(90))}",
            "P_ate_2032": (primeiro <= 2032).mean(), "P_ate_2040": (primeiro <= 2040).mean(),
            "P_ate_2060": (primeiro <= 2060).mean(), "pct_2032": np.median(parte[:, anos.index(2032)]),
            "pct_2040": np.median(parte[:, anos.index(2040)])}


def queda_necessaria(l0):
    """Queda uniforme da procura que põe 50% + 1 dos cursos abaixo de 1 candidato por vaga."""
    k = len(l0) // 2 + 1
    return np.exp(-np.sort(l0.values)[k - 1]) - 1


def teste_retroativo(s, sig_ruido, sig_nivel):
    """Do corte, sem conhecer o futuro: o % observado cai dentro da faixa de 80%?"""
    for corte, alvo in [(2014, 2017), (2017, 2022), (2017, 2026), (2020, 2026), (2022, 2026)]:
        l0 = niveis(s, corte, 3)
        g = choques_anuais(s, corte)
        anos = list(range(corte + 1, alvo + 1))
        real = s[s["Ano"] == alvo].set_index("Curso_Ref")["Cand_Vaga"].reindex(l0.index).dropna()
        l0 = l0.loc[real.index]
        for rotulo, t in [("tendência zero", 0.0), ("tendência do histórico", g.loc[g.index >= 2009, "mediana"].sum() / g.loc[g.index >= 2009, "gap"].sum())]:
            parte = simular(l0, np.full(len(anos), t), g["por_ano"].values, sig_ruido, sig_nivel, anos)[:, -1]
            print(f"  {corte}->{alvo} {rotulo:24}: previsto {np.median(parte):5.1%} "
                  f"[{np.percentile(parte, 10):5.1%},{np.percentile(parte, 90):5.1%}]; real {(real < 1).mean():5.1%} ({len(real)} cursos)")


def grafico(trajetorias, anos, hist, n_cursos):
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    cores = {"Sem tendência": "#6B7280", "Demografia (IBGE)": "#2563EB", "Queda 2012–2026": "#D97706", "Queda 2017–2026": "#B91C1C"}
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(hist.index, hist.values * 100, "o-", color="#111827", ms=4, lw=2)
    ax.annotate("observado", (2022, hist.loc[2022] * 100), xytext=(2013.5, 36), color="#111827")
    fim = {a: anos.index(a) for a in (2045,)}
    for nome, parte in trajetorias.items():
        med = np.median(parte, 0) * 100
        if nome != "Demografia (IBGE)":  # a faixa quase coincide com a de "sem tendência"
            ax.fill_between(anos, np.percentile(parte, 10, 0) * 100, np.percentile(parte, 90, 0) * 100, color=cores[nome], alpha=0.10, lw=0)
        ax.plot(anos, med, color=cores[nome], lw=2)
        ajuste = {"Demografia (IBGE)": 3.5, "Sem tendência": -3.5}.get(nome, 7)
        ax.annotate(nome, (2045, med[fim[2045]]), xytext=(2043, med[fim[2045]] + ajuste), va="center", color="#374151", fontsize=10)
    ax.axhline((n_cursos // 2 + 1) / n_cursos * 100, color="#111827", lw=1, ls="--")
    ax.annotate("50% + 1 dos cursos", (2012, 52), color="#111827")
    ax.set_xlim(2012, 2054); ax.set_ylim(0, 100)
    ax.set_ylabel("% de cursos com menos de 1 candidato por vaga")
    ax.set_title("Só uma queda contínua leva a maioria dos cursos à sobra (faixa: 80% das simulações)", loc="left", fontsize=12)
    ax.grid(axis="y", color="#E5E7EB", lw=0.8); ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIG, "05_projecao_maioria_sobra.png"), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    s = carregar()
    g = choques_anuais(s)
    print(g.round(3).to_string())
    sig_ruido, sig_nivel = variancias(s, g)
    print(f"desvio: ruído de um ano {sig_ruido:.3f}; mudança de nível {sig_nivel:.3f}")

    media = lambda desde: g.loc[g.index > desde, "mediana"].sum() / g.loc[g.index > desde, "gap"].sum()  # noqa: E731
    anos = list(range(ANO_INICIO + 1, ANO_FIM + 1))
    pop = pd.read_csv(ARQUIVO_POP).set_index("ano")["populacao_15a19"]
    d_pop = np.log(pop).diff().reindex(anos).values
    print("tendência anual em log:", {a: round(media(a), 3) for a in (2012, 2017, 2021)}, "demografia 2026-2040:", round(np.log(pop[2040] / pop[2026]) / 14, 4))
    print("população 15-19 PR 2017->2026:", round(pop[2026] / pop[2017] - 1, 3), "; mediana cand/vaga 2017->2026 (log):", round(g.loc[g.index > 2017, "mediana"].sum(), 3))

    for rotulo, minimo in [("todos os cursos de 2026", 1), ("só cursos com 3+ anos", 3)]:
        l0 = niveis(s, minimo=minimo)
        ate = g.loc[g.index > 2012, "por_ano"]
        # A variação mediana de 2021 para 2026 soma zero: "sem tendência" é o ritmo dos últimos 5 anos
        cen = {"Sem tendência": np.zeros(len(anos)),
               "Demografia (IBGE)": d_pop,
               "Queda 2012–2026": np.full(len(anos), media(2012)),
               "Queda 2017–2026": np.full(len(anos), media(2017))}
        nov = {}
        trajetorias = {}
        for nome, t in cen.items():
            parte = simular(l0, t, ate.values, sig_ruido, sig_nivel, anos, incerteza=0.005)
            nov[nome] = tabela_cenarios(parte, anos, len(l0))
            trajetorias[nome] = parte
        print(f"\n--- {rotulo}: {len(l0)} cursos; limite {len(l0) // 2 + 1}; nível atual abaixo de 1: {(l0 < 0).sum()} ({(l0 < 0).mean():.0%}); "
              f"queda uniforme necessária: {queda_necessaria(l0):.0%}")
        print(pd.DataFrame(nov).T.to_string())
        q = queda_necessaria(l0)
        for taxa in (-0.01, -0.02, -0.03, -0.05):
            print(f"  queda constante de {-taxa:.0%} ao ano: maioria em {ANO_INICIO + int(np.ceil(np.log(1 + q) / np.log(1 + taxa)))}")
        if minimo == 1:
            base = s[s["Ano"] >= 2012].groupby("Ano")["Cand_Vaga"].apply(lambda x: (x < 1).mean())
            grafico(trajetorias, anos, base, len(l0))

    print("\n--- teste do simulador em anos passados")
    teste_retroativo(s, sig_ruido, sig_nivel)
