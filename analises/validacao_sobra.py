import os
import warnings

import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pipeline.db import RAIZ
from pipeline.cursos import chave_curso

# Valida o indicador de sobra (cand/vaga < 1) com os relatórios oficiais de ocupação das vagas do NC-UFPR.
# "Sobrou vaga" = mesmo somando a chamada geral e todas as complementares, o nº de aprovados ficou abaixo
# das vagas do curso. Gera os números de analises/02_validacao_sobra.md e a figura 04.
#
#   python -m analises.validacao_sobra

warnings.filterwarnings("ignore")
FAIXAS = [0, 0.5, 1, 1.5, 2, 3, 5, 1000]
ROTULOS = ["0–0,5", "0,5–1", "1–1,5", "1,5–2", "2–3", "3–5", "> 5"]


def cruzar():
    h = pd.read_csv(os.path.join(RAIZ, "data", "gold", "historico_candidato_vaga.csv"))
    h = h[~h["Curso"].str.contains("Policial|Bombeiro|CFO|Cadete", case=False, na=False)]
    h = h[(h["Vagas"] > 0) & h["Concorrentes"].notna()].copy()
    o = pd.read_csv(os.path.join(RAIZ, "data", "silver", "nc_ocupacao_por_curso.csv"))
    o = o.pivot_table(index=["ano", "curso"], columns="tipo", values="aprovados").reset_index()
    h["k"] = h["Curso"].map(chave_curso)
    o["k"] = o["curso"].map(chave_curso)
    m = h.merge(o, left_on=["Ano", "k"], right_on=["ano", "k"], how="inner")
    m = m[m["final"].notna()].copy()  # 2016-2022 (2023 só tem a chamada geral)
    m["sobrou_vaga"] = m["final"] < m["Vagas"]
    m["ocupacao_final"] = m["final"] / m["Vagas"]
    m["faixa"] = pd.cut(m["Cand_Vaga"], FAIXAS, labels=ROTULOS)
    return m


def limites(m):
    linhas = []
    total = m["sobrou_vaga"].sum()
    for lim in [1, 1.5, 2, 2.5, 3]:
        p = m["Cand_Vaga"] < lim
        acertos = (p & m["sobrou_vaga"]).sum()
        alarmes = (p & ~m["sobrou_vaga"]).sum()
        linhas.append({"limite": lim, "sobras_detectadas": f"{acertos}/{total}", "recall": acertos / total,
                       "alarmes_falsos": alarmes, "precisao": acertos / max(acertos + alarmes, 1)})
    return pd.DataFrame(linhas)


def grafico(por_faixa):
    os.makedirs(os.path.join(RAIZ, "analises", "figuras"), exist_ok=True)
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(9, 4.5))
    cores = ["#B23A3A" if v >= 0.5 else ("#E07B39" if v >= 0.05 else "#4A90D9") for v in por_faixa["sobrou"]]
    barras = ax.bar(por_faixa.index.astype(str), por_faixa["sobrou"] * 100, color=cores)
    for b, (n, v) in zip(barras, zip(por_faixa["pares"], por_faixa["sobrou"])):
        ax.text(b.get_x() + b.get_width() / 2, v * 100 + 2, f"{v:.0%}\n(n={n})", ha="center", fontsize=9)
    ax.set_ylim(0, 118)
    ax.set_xlabel("candidatos por vaga no vestibular")
    ax.set_ylabel("% com vaga sem preencher")
    ax.set_title("Cursos que terminaram com vaga sobrando (ocupação oficial 2016–2022)")
    fig.tight_layout()
    fig.savefig(os.path.join(RAIZ, "analises", "figuras", "04_validacao_sobra.png"), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    m = cruzar()
    por_faixa = m.groupby("faixa", observed=True).agg(
        pares=("sobrou_vaga", "size"), sobrou=("sobrou_vaga", "mean"), ocupacao_final_mediana=("ocupacao_final", "median"))
    grafico(por_faixa)
    print(f"Pares curso-ano com resumo final (2016-2022): {len(m)} | terminaram com vaga sobrando: "
          f"{m['sobrou_vaga'].sum()} ({m['sobrou_vaga'].mean():.0%})\n")
    print(por_faixa.round(2).to_string())
    print("\n" + limites(m).round(2).to_string(index=False))
