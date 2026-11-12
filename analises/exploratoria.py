import os
import warnings

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pipeline.db import RAIZ
from pipeline.cursos import mapear_historico, chave_curso

# Análise exploratória do histórico de candidato/vaga (data/gold/historico_candidato_vaga.csv).
# Gera os números citados em analises/01_exploratoria.md e os gráficos em analises/figuras/.
# Não acessa banco nem internet.
#
#   python -m analises.exploratoria

warnings.filterwarnings("ignore")
PASTA_FIG = os.path.join(RAIZ, "analises", "figuras")
AZUL, AZUL_CLARO, CINZA, LARANJA = "#0D3C67", "#4A90D9", "#9AA5B1", "#E07B39"

# Totais divulgados pela UFPR em notícias, usados para conferir a base
INSCRITOS_NOTICIA = {2020: 38453, 2024: 36160, 2025: 36969, 2026: 39565, 2027: 43290}


def carregar():
    h = pd.read_csv(os.path.join(RAIZ, "data", "gold", "historico_candidato_vaga.csv"))
    # Formação de oficiais da PM/Bombeiros não é curso de graduação da UFPR
    return h[~h["Curso"].str.contains("Policial|Bombeiro|CFO|Cadete", case=False, na=False)]


def totais_por_ano(h):
    g = h.groupby("Ano").agg(
        cursos=("Curso", "size"),
        concorrentes=("Concorrentes", "sum"),
        treineiros=("Treineiros", "sum"),
        vagas=("Vagas", "sum"),
        linhas_sem_vagas=("Vagas", lambda s: s.isna().sum()),
    )
    g["inscritos"] = g["concorrentes"] + g["treineiros"]
    validos = h[h["Vagas"] > 0]
    g["mediana_cand_vaga"] = validos.groupby("Ano")["Cand_Vaga"].median()
    g["pct_cursos_abaixo_2"] = validos.groupby("Ano")["Cand_Vaga"].apply(lambda s: (s < 2).mean())
    g["pct_sem_vagas"] = g["linhas_sem_vagas"] / g["cursos"]
    return g


def series_por_curso(h):
    m = mapear_historico(h, ano_ref=2026)
    m = m[m["Curso_Ref"].notna()].groupby(["Curso_Ref", "Ano"], as_index=False)[["Concorrentes", "Vagas"]].sum(min_count=1)
    chaves = m["Curso_Ref"].map(chave_curso)
    m["local"] = np.where(chaves.map(lambda k: k[2]) == "Curitiba", "Curitiba", "Interior")
    m["turno"] = chaves.map(lambda k: {"I": "Integral", "M": "Manhã", "T": "Tarde", "N": "Noite"}.get(k[3], "Outros"))
    return m


def indice_por_grupo(m, coluna, anos=(2017, 2021, 2026)):
    p = m.pivot_table(index="Curso_Ref", columns="Ano", values="Concorrentes")
    completos = p[list(anos)].dropna()
    grupos = m.drop_duplicates("Curso_Ref").set_index("Curso_Ref")[coluna]
    t = completos.join(grupos).groupby(coluna)[list(anos)].sum()
    return (t.div(t[anos[0]], axis=0) * 100).round(0), len(completos)


def persistencia(h, m):
    total = h.groupby("Ano").apply(lambda d: d["Concorrentes"].sum() + d["Treineiros"].fillna(0).sum())
    d = m[m["Concorrentes"] > 0].sort_values(["Curso_Ref", "Ano"]).copy()
    d["ano_ant"] = d.groupby("Curso_Ref")["Ano"].shift()
    d["c_ant"] = d.groupby("Curso_Ref")["Concorrentes"].shift()
    d = d[(d["Ano"] - d["ano_ant"]) == 1].copy()
    d["dlog"] = np.log(d["Concorrentes"] / d["c_ant"])
    media_ano = d.groupby("Ano")["dlog"].transform("mean")
    r2_ano = 1 - ((d["dlog"] - media_ano) ** 2).sum() / ((d["dlog"] - d["dlog"].mean()) ** 2).sum()
    d["res"] = d["dlog"] - media_ano
    d["res_ant"] = d.groupby("Curso_Ref")["res"].shift()
    reversao = d["res"].corr(d["res_ant"])
    erro_ano = np.mean(np.abs(d["c_ant"] - d["Concorrentes"]) / d["Concorrentes"])
    return {"pares": len(d), "r2_ano": r2_ano, "reversao": reversao, "erro_repetir": erro_ano, "total": total}


def graficos(g, idx_local, idx_turno):
    os.makedirs(PASTA_FIG, exist_ok=True)
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

    # 1. Inscritos e vagas por ano
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(g.index, g["inscritos"] / 1000, "o-", color=AZUL, label="Inscritos (concorrentes + treineiros)")
    ax.plot(g.index, g["vagas"] / 1000, "s--", color=CINZA, label="Vagas na base")
    ax.plot([2027], [INSCRITOS_NOTICIA[2027] / 1000], "*", color=LARANJA, markersize=14, label="2027 (notícia UFPR)")
    for a in (2004, 2018, 2019):
        ax.axvspan(a - 0.5, a + 0.5, color="#EEEEEE", zorder=0)
    ax.axvspan(2019.5, 2021.5, color="#FBE3D6", zorder=0, label="Pandemia")
    ax.set_ylabel("milhares")
    ax.set_title("Inscritos no vestibular da UFPR (cinza: anos sem dado por curso)")
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIG, "01_inscritos_vagas.png"), dpi=130)
    plt.close(fig)

    # 2. Mediana de cand/vaga e lacuna de vagas
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(g.index, g["mediana_cand_vaga"], "o-", color=AZUL, label="Mediana de cand/vaga por curso")
    ax.set_ylabel("candidatos por vaga")
    ax2 = ax.twinx()
    ax2.bar(g.index, g["pct_sem_vagas"] * 100, color=LARANJA, alpha=0.35, label="% de cursos sem vagas na base")
    ax2.set_ylabel("% sem vagas")
    ax2.spines["top"].set_visible(False)
    ax.set_title("Concorrência típica caiu de ~11 para ~2,4; desde 2021 falta o nº de vagas de 1/4 dos cursos")
    linhas = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    ax.legend(linhas, [l.get_label() for l in linhas], frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIG, "02_mediana_e_lacunas.png"), dpi=130)
    plt.close(fig)

    # 3. Índice de candidatos por grupo (2017 = 100)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, (titulo, idx) in zip(axes, [("Local", idx_local), ("Turno", idx_turno)]):
        for i, (grupo, linha) in enumerate(idx.iterrows()):
            ax.plot([str(c) for c in idx.columns], linha.values, "o-", label=grupo,
                    color=[AZUL, LARANJA, AZUL_CLARO, CINZA, "#5B8C5A"][i % 5])
        ax.axhline(100, color="#CCCCCC", lw=1)
        ax.set_title(f"Candidatos por {titulo.lower()} (2017 = 100)")
        ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIG, "03_indice_grupos.png"), dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    h = carregar()
    g = totais_por_ano(h)
    m = series_por_curso(h)
    idx_local, n_local = indice_por_grupo(m, "local")
    idx_turno, _ = indice_por_grupo(m, "turno")
    p = persistencia(h, m)
    graficos(g, idx_local, idx_turno)

    print("== Totais por ano ==")
    print(g[["cursos", "inscritos", "vagas", "pct_sem_vagas", "mediana_cand_vaga", "pct_cursos_abaixo_2"]].round(2).to_string())
    print("\n== Conferência com notícias da UFPR (inscritos) ==")
    for ano, valor in INSCRITOS_NOTICIA.items():
        base = g["inscritos"].get(ano)
        print(f"{ano}: notícia {valor} | base {int(base) if pd.notna(base) else '-'}")
    print(f"\n== Índice de candidatos ({n_local} cursos com 2017, 2021 e 2026) ==")
    print(idx_local.to_string())
    print(idx_turno.to_string())
    print("\n== Dinâmica ano a ano por curso ==")
    print(f"pares de anos consecutivos: {p['pares']}")
    print(f"variação explicada pelo efeito comum do ano: {p['r2_ano']:.0%}")
    print(f"correlação da variação própria com a do ano seguinte: {p['reversao']:+.2f}")
    print(f"erro médio de repetir os candidatos do ano anterior: {p['erro_repetir']:.0%}")
    print(f"\nGráficos em {os.path.relpath(PASTA_FIG, RAIZ)}")
