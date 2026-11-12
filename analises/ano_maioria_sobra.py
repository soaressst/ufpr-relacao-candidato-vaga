"""Estima o ano em que 50% + 1 dos cursos terão sobra, combinando projeções testadas em anos passados.

1. Testa, em cortes passados, várias formas de projetar o % de cursos abaixo de 1 candidato por vaga.
2. Dá a cada projeção um peso pelo seu erro nesse teste (1 / erro quadrático, horizontes de 3+ anos).
3. Simula o futuro com cada projeção e junta as simulações conforme os pesos.

Três definições de sobra: menos candidatos do que vagas; curso que termina com vaga sem preencher
(probabilidades de 02_validacao_sobra.md); e 50% do total de vagas sem preencher (ocupação mediana).

Uso: python -W ignore -m analises.ano_maioria_sobra
"""
import os
import warnings

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.tsa.statespace.structural import UnobservedComponents

from analises.causas_baixa_procura import carregar as carregar_causas
from analises.projecao_maioria_sobra import ARQUIVO_POP, carregar, choques_anuais, niveis, variancias
from analises.validacao_sobra import cruzar
from pipeline.db import RAIZ

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ORIGENS = [2012, 2013, 2014, 2015, 2016, 2017, 2020, 2021, 2022, 2023, 2024, 2025]
N_SIM = 4000
INSCRITOS_2026, INSCRITOS_2027 = 39565, 43290  # divulgados pela UFPR
ELASTICIDADE = 0.91  # analises/comparacao_hierarquico.py: 1% nos inscritos move o nível comum em ~0,91%
ANOS = list(range(2027, 2061))
LIM_FAIXA = [0.5, 1, 1.5, 2, 3, 5]
P_SOBRA = np.array([1.0, 1.0, 0.57, 0.09, 0.05, 0.02, 0.0])  # 02_validacao_sobra.md
SEM_OCUPAR = np.array([0.82, 0.49, 0.14, 0.0, 0.0, 0.0, 0.0])  # 1 - ocupação final mediana, limitada a 100%


def media_desde(g, inicio):
    d = g[g.index > inicio]
    return d["mediana"].sum() / d["gap"].sum() if len(d) else 0.0


def indice_anual(g):
    i = g["mediana"].cumsum()
    return i.reindex(range(int(g.index[0]), int(g.index[-1]) + 1))


def inclinacao_uc(g, especificacao):
    """Tendência final de um modelo de componentes não observados no nível comum."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = UnobservedComponents(indice_anual(g).values, especificacao).fit(disp=False, maxiter=200)
    return float(r.trend["smoothed"][-1])


def caminhos(g, ano, pop, n):
    """Tendência do nível comum por ano à frente, com dados só até `ano`. Cada método devolve array(n)."""
    toda = media_desde(g, g.index[0] - 1)
    h = np.arange(1, n + 1)
    dpop = np.log(pop).diff().reindex(range(ano + 1, ano + n + 1)).fillna(0).values
    c = {"sem_tendencia": np.zeros(n),
         "media_historica": np.full(n, toda),
         "media_10_anos": np.full(n, media_desde(g, ano - 10)),
         "media_5_anos": np.full(n, media_desde(g, ano - 5)),
         "amortecida": toda * 0.9 ** h,
         "populacao": dpop}
    try:
        c["uc_tendencia_local"] = np.full(n, inclinacao_uc(g, "local linear trend"))
    except Exception:
        c["uc_tendencia_local"] = np.full(n, toda)
    try:
        c["uc_com_deriva"] = np.full(n, inclinacao_uc(g, "random walk with drift"))
    except Exception:
        c["uc_com_deriva"] = np.full(n, toda)
    return c


def share_esperado(nivel, deslocamento, sig):
    return norm.cdf((-nivel - deslocamento) / sig).mean()


def teste_retroativo(s, pop, sig):
    linhas = []
    for o in ORIGENS:
        g = choques_anuais(s, o)
        l0 = niveis(s, o, 3)
        n = 2026 - o
        cam = caminhos(g, o, pop, n)
        for t in range(o + 1, 2027):
            real = s[s["Ano"] == t].set_index("Curso_Ref")["Cand_Vaga"].reindex(l0.index).dropna()
            if real.empty:
                continue
            l = l0.loc[real.index]
            base_real = (real < 1).mean()
            for nome, tr in cam.items():
                previsto = share_esperado(l.values, tr[: t - o].sum(), sig)
                linhas.append({"origem": o, "alvo": t, "h": t - o, "metodo": nome, "previsto": previsto, "real": base_real})
            atual = s[s["Ano"] == o].set_index("Curso_Ref")["Cand_Vaga"].reindex(l.index)
            linhas.append({"origem": o, "alvo": t, "h": t - o, "metodo": "repetir_percentual", "previsto": (atual < 1).mean(), "real": base_real})
    return pd.DataFrame(linhas)


def primeiro(serie, limite):
    cruz = serie >= limite
    return np.where(cruz.any(1), np.array(ANOS)[cruz.argmax(1)], 9999)


def simular_tudo(l0, vagas, tendencia, choques, sig_ruido, sig_nivel, seed, incerteza=0.005):
    rng = np.random.default_rng(seed)
    nivel = np.tile(l0, (N_SIM, 1))
    desvio = rng.normal(0, incerteza, N_SIM)[:, None]
    n_ano = len(ANOS)
    a, b, c = np.zeros((N_SIM, n_ano)), np.zeros((N_SIM, n_ano)), np.zeros((N_SIM, n_ano))
    peso = vagas / vagas.sum()
    for i in range(n_ano):
        nivel = nivel + tendencia[i] + desvio + rng.choice(choques, N_SIM)[:, None] + rng.normal(0, sig_nivel, nivel.shape)
        obs = np.exp(nivel + rng.normal(0, sig_ruido, nivel.shape))
        faixa = np.digitize(obs, LIM_FAIXA)
        a[:, i] = (obs < 1).mean(1)
        b[:, i] = P_SOBRA[faixa].mean(1)
        c[:, i] = (SEM_OCUPAR[faixa] * peso).sum(1)
    return a, b, c


def prob_acumulada(anos_cruz, pesos):
    return [float(pesos[anos_cruz <= a].sum() / pesos.sum()) for a in ANOS]


def grafico(curvas):
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(10, 5))
    cores = {"Menos candidatos que vagas": "#2563EB", "Curso termina com vaga sobrando": "#D97706"}
    for nome, valores in curvas.items():
        ax.plot(ANOS, np.array(valores) * 100, color=cores[nome], lw=2.2)
    ax.axhline(50, color="#111827", lw=1, ls="--")
    ax.text(2027.3, 52, "50% de chance", color="#111827")
    fim = ANOS.index(2052)
    for nome, valores in curvas.items():
        desloc = 3.5 if nome.startswith("Curso") else -10
        ax.text(2042, np.array(valores)[fim] * 100 + desloc, nome, color="#374151", fontsize=10)
    ax.set_xlim(2027, 2060); ax.set_ylim(0, 100)
    ax.set_ylabel("chance de 50% + 1 dos cursos já terem cruzado (%)")
    ax.set_title("Metade dos cursos com sobra: chance de 50% por volta de 2034 ou 2042, conforme a definição", loc="left", fontsize=12)
    ax.grid(axis="y", color="#E5E7EB", lw=0.8); ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(os.path.join(RAIZ, "analises", "figuras", "06_ano_maioria_sobra.png"), dpi=130)
    plt.close(fig)


def resumo_ano(anos_cruz, pesos=None):
    pesos = np.full(len(anos_cruz), 1 / len(anos_cruz)) if pesos is None else pesos / pesos.sum()
    ordem = np.argsort(anos_cruz)
    acum = np.cumsum(pesos[ordem])
    q = lambda p: anos_cruz[ordem][np.searchsorted(acum, p)]  # noqa: E731
    txt = lambda v: "depois de 2060" if v == 9999 else str(int(v))  # noqa: E731
    return {"mediana": txt(q(0.5)), "p10": txt(q(0.1)), "p25": txt(q(0.25)), "p75": txt(q(0.75)), "p90": txt(q(0.9)),
            "ate_2030": float(pesos[anos_cruz <= 2030].sum()), "ate_2035": float(pesos[anos_cruz <= 2035].sum()),
            "ate_2040": float(pesos[anos_cruz <= 2040].sum()), "ate_2050": float(pesos[anos_cruz <= 2050].sum()),
            "ate_2060": float(pesos[anos_cruz <= 2060].sum())}


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    s = carregar()
    pop = pd.read_csv(ARQUIVO_POP).set_index("ano")["populacao_15a19"]
    g = choques_anuais(s)
    sig_ruido, sig_nivel = variancias(s, g)
    sig = float(np.hypot(sig_ruido, 0.0))

    print("--- % real de cursos que terminaram com vaga sobrando (relatórios de ocupação)")
    m = cruzar()
    print(m.groupby("ano").agg(pares=("sobrou_vaga", "size"), sobrou=("sobrou_vaga", "mean"),
                               abaixo_de_1=("Cand_Vaga", lambda x: (x < 1).mean())).round(3).to_string())

    print("\n--- teste das projeções em anos passados (erro em pontos percentuais do % de cursos abaixo de 1)")
    t = teste_retroativo(s, pop, sig)
    t.to_csv("analises/resultados_projecao_percentual.csv", index=False)
    t["erro"] = (t["previsto"] - t["real"]).abs() * 100
    t["viés"] = (t["previsto"] - t["real"]) * 100
    t["faixa_h"] = pd.cut(t["h"], [0, 2, 5, 20], labels=["1-2 anos", "3-5 anos", "6+ anos"])
    print(t.pivot_table(index="metodo", columns="faixa_h", values="erro", observed=True).round(1).sort_values("3-5 anos").to_string())
    print(t.pivot_table(index="metodo", columns="faixa_h", values="viés", observed=True).round(1).to_string())
    longo = t[t["h"] >= 3]
    print("pares com 3+ anos:", longo.groupby("metodo").size().iloc[0])
    eqm = ((longo["previsto"] - longo["real"]) ** 2).groupby(longo["metodo"]).mean()
    pesos = (1 / eqm).drop("repetir_percentual")
    pesos = pesos / pesos.sum()
    print("pesos:", pesos.round(3).to_dict())

    causas = carregar_causas()
    vagas_26 = causas[causas["Ano"] == 2026].set_index("Curso_Ref")["vagas_usadas"]
    d = g
    choques = np.repeat(d["por_ano"].values, d["gap"].astype(int).values)
    choques = choques - choques.mean()
    cam = caminhos(g, 2026, pop, len(ANOS))
    print("\ntendência por método (log por ano, primeiros 3 anos):", {k: np.round(v[:3], 3).tolist() for k, v in cam.items()})

    for rotulo, minimo in [("141 cursos", 1), ("cursos com 3+ anos", 3)]:
        l = niveis(s, minimo=minimo)
        vagas = vagas_26.reindex(l.index).fillna(vagas_26.median()).values
        lim = (len(l) // 2 + 1) / len(l)
        juntos = {"menos candidatos que vagas": ([], []), "curso termina com vaga sobrando": ([], []), "50% das vagas sem ocupar": ([], [])}
        trajetos = {k: [] for k in juntos}
        for i, nome in enumerate(cam):
            a, b, c = simular_tudo(l.values, vagas, cam[nome], choques, sig_ruido, sig_nivel, 10 + i)
            for chave, serie, limite in [("menos candidatos que vagas", a, lim), ("curso termina com vaga sobrando", b, lim),
                                         ("50% das vagas sem ocupar", c, 0.5)]:
                cr = primeiro(serie, limite)
                juntos[chave][0].append(cr)
                juntos[chave][1].append(np.full(len(cr), pesos[nome]))
                trajetos[chave].append((nome, np.median(serie, 0)))
                if chave == "menos candidatos que vagas":
                    print(f"  [{rotulo}] {nome:20} tendência {cam[nome][:5].mean():+.3f}: {resumo_ano(cr)}")
        print(f"\n=== {rotulo}: limite {len(l) // 2 + 1} de {len(l)}")
        for chave, (cr, p) in juntos.items():
            print(f"{chave:34} com pesos : {resumo_ano(np.concatenate(cr), np.concatenate(p))}")
            print(f"{'':34} pesos iguais: {resumo_ano(np.concatenate(cr))}")
        if minimo == 1:
            grafico({"Menos candidatos que vagas": prob_acumulada(np.concatenate(juntos["menos candidatos que vagas"][0]), np.concatenate(juntos["menos candidatos que vagas"][1])),
                     "Curso termina com vaga sobrando": prob_acumulada(np.concatenate(juntos["curso termina com vaga sobrando"][0]), np.concatenate(juntos["curso termina com vaga sobrando"][1]))})
            salto = ELASTICIDADE * np.log(INSCRITOS_2027 / INSCRITOS_2026)
            crA, crB, ps = [], [], []
            for i, nome in enumerate(cam):
                a, b, _ = simular_tudo(l.values + salto, vagas, cam[nome], choques, sig_ruido, sig_nivel, 50 + i)
                crA.append(primeiro(a, lim)); crB.append(primeiro(b, lim)); ps.append(np.full(N_SIM, pesos[nome]))
            print(f"sensibilidade com os inscritos de 2027 (+{salto:.3f} no nível de partida):")
            print("  menos candidatos que vagas     :", resumo_ano(np.concatenate(crA), np.concatenate(ps)))
            print("  curso termina com vaga sobrando:", resumo_ano(np.concatenate(crB), np.concatenate(ps)))
            a0, b0, c0 = simular_tudo(l.values, vagas, np.zeros(len(ANOS)), np.zeros(1), sig_ruido, 0.0, 1, 0.0)
            print(f"ponto de partida 2027 sem choque: abaixo de 1 {np.median(a0[:, 0]):.1%}; termina com sobra {np.median(b0[:, 0]):.1%}; vagas sem ocupar {np.median(c0[:, 0]):.1%}")
