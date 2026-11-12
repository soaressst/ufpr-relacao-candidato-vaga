"""Investiga o que os cursos com poucos candidatos por vaga têm em comum.

São associações nos dados, não prova de causa. Usa a média de 2024-2026 para reduzir o ruído de um
ano só. Cand/vaga contra as vagas de referência, como no modelo.

Uso: python -W ignore -m analises.causas_baixa_procura
"""
import re

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pipeline import modelo_previsao as mp
from pipeline.cursos import chave_curso

AREAS = [
    ("Saúde", r"medicina|enfermagem|farmacia|odontologia|nutricao|fisioterapia|terapia|biomedicina|saude coletiva|psicologia"),
    ("Computação", r"computacao|informatica|sistemas|inteligencia artificial|estatistica"),
    ("Engenharias", r"engenharia|arquitetura|geologia"),
    ("Agrárias e ambiente", r"agronomia|zootecnia|agroecologia|ambient|florestal|oceanografia"),
    ("Exatas e naturais", r"fisica|matematica|quimica|ciencias exatas|ciencias biologicas|^ciencias$|expressao grafica"),
    ("Letras", r"letras|linguagem"),
    ("Artes e design", r"artes|musica|design|luteria|producao cultural"),
    ("Gestão e negócios", r"administracao|contabeis|economicas|gestao|secretariado|negocios|turismo"),
    ("Humanas e direito", r"direito|historia|filosofia|geografia|sociais|servico social|pedagogia|educacao fisica|jornalismo|publicidade|relacoes publicas|comunicacao"),
]


def area(nome):
    for rotulo, padrao in AREAS:
        if re.search(padrao, nome):
            return rotulo
    return "Outras"


def carregar():
    s = mp.preparar_series(pd.read_csv(mp.ARQUIVO_HISTORICO)).copy()
    chaves = {c: chave_curso(c) for c in s["Curso_Ref"].unique()}
    s["nome"] = s["Curso_Ref"].map(lambda c: chaves[c][0])
    s["grau"] = s["Curso_Ref"].map(lambda c: chaves[c][1] or "Sem grau")
    s["cidade"] = s["Curso_Ref"].map(lambda c: chaves[c][2])
    s["turno"] = s["Curso_Ref"].map(lambda c: {"N": "Noturno", "I": "Integral"}.get(chaves[c][3], "Parcial diurno"))
    s["local"] = np.where(s["cidade"] == "Curitiba", "Curitiba", "Interior e litoral")
    s["area"] = s["nome"].map(area)
    s["vagas_usadas"] = s["Vagas"].where(s["Ano"] < mp.ANO_CORTE_VAGAS, s["Vagas_Referencia"].fillna(s["Vagas"]))
    s["candidatos"] = s["Cand_Vaga"] * s["vagas_usadas"]
    return s


def taxa_por_grupo(atual, coluna):
    t = atual.groupby(coluna).agg(cursos=("cv", "size"), abaixo_de_1=("cv", lambda x: (x < 1).mean()),
                                  mediana=("cv", "median"), vagas=("vagas", "median"))
    return t.sort_values("abaixo_de_1", ascending=False).round(2)


def regressao(atual):
    d = atual[atual["cv"] > 0].assign(log_cv=lambda x: np.log(x["cv"]), log_vagas=lambda x: np.log(x["vagas"]))
    m = smf.ols("log_cv ~ C(local, Treatment('Curitiba')) + C(turno, Treatment('Integral'))"
                " + C(grau, Treatment('Bacharelado')) + C(area, Treatment('Saúde')) + log_vagas",
                data=d).fit(cov_type="HC3")
    t = pd.DataFrame({"efeito_pct": (np.exp(m.params) - 1) * 100, "p": m.pvalues}).round(3)
    print(t.to_string())
    print(f"R² = {m.rsquared:.2f}, n = {int(m.nobs)}")
    # Quanto cada bloco explica sozinho
    for rotulo, f in [("só local", "C(local)"), ("só grau", "C(grau)"), ("só turno", "C(turno)"), ("só área", "C(area)"),
                      ("só nº de vagas", "log_vagas"), ("sem área", "C(local) + C(turno) + C(grau) + log_vagas")]:
        print(f"  R² {rotulo}: {smf.ols('log_cv ~ ' + f, data=d).fit().rsquared:.2f}")


def decompor(s):
    """Queda de cand/vaga 2017->2026 nos cursos que existem nos dois anos: veio de candidatos ou de vagas?"""
    a = s[s["Ano"] == 2017].set_index("Curso_Ref")
    b = s[s["Ano"] == 2026].set_index("Curso_Ref")
    c = a.index.intersection(b.index)
    d = pd.DataFrame({"cand_17": a.loc[c, "candidatos"], "cand_26": b.loc[c, "candidatos"], "vagas_17": a.loc[c, "vagas_usadas"],
                      "vagas_26": b.loc[c, "vagas_usadas"], "cv_17": a.loc[c, "Cand_Vaga"], "cv_26": b.loc[c, "Cand_Vaga"],
                      "local": b.loc[c, "local"], "grau": b.loc[c, "grau"], "area": b.loc[c, "area"]})
    print(f"{len(d)} cursos; candidatos {d.cand_17.sum():.0f} -> {d.cand_26.sum():.0f}; vagas {d.vagas_17.sum():.0f} -> {d.vagas_26.sum():.0f}")
    print(f"mediana candidatos 2026/2017: {(d.cand_26 / d.cand_17).median():.2f}; mediana vagas 2026/2017: {(d.vagas_26 / d.vagas_17).median():.2f}")
    novos_abaixo = d[(d.cv_17 >= 1) & (d.cv_26 < 1)]
    print(f"caíram abaixo de 1 entre 2017 e 2026: {len(novos_abaixo)}; candidatos {novos_abaixo.cand_17.sum():.0f} -> "
          f"{novos_abaixo.cand_26.sum():.0f}; vagas {novos_abaixo.vagas_17.sum():.0f} -> {novos_abaixo.vagas_26.sum():.0f}")
    for g in ["local", "grau", "area"]:
        print((d.groupby(g).agg(cursos=("cv_17", "size"), cand_17=("cand_17", "sum"), cand_26=("cand_26", "sum"),
                                vagas_17=("vagas_17", "sum"), vagas_26=("vagas_26", "sum"))
               .assign(var_cand=lambda x: x.cand_26 / x.cand_17 - 1, var_vagas=lambda x: x.vagas_26 / x.vagas_17 - 1)
               .sort_values("var_cand").round(2)).to_string())


def oferta_total():
    """Inscritos e vagas de todas as linhas do histórico, por ano."""
    h = pd.read_csv(mp.ARQUIVO_HISTORICO)
    t = h.groupby("Ano").agg(concorrentes=("Concorrentes", "sum"), vagas=("Vagas", "sum"), nomes=("Curso", "nunique"))
    t["cand_por_vaga"] = t["concorrentes"] / t["vagas"]
    print(t.round(2).to_string())


if __name__ == "__main__":
    s = carregar()
    pd.set_option("display.width", 200)
    atual = (s[s["Ano"] >= 2024].groupby("Curso_Ref")
             .agg(cv=("Cand_Vaga", "mean"), vagas=("vagas_usadas", "last"), ultimo=("Ano", "max"), nome=("nome", "last"),
                  grau=("grau", "last"), cidade=("cidade", "last"), turno=("turno", "last"), local=("local", "last"), area=("area", "last")))
    atual = atual[atual["ultimo"] == 2026]
    print(f"{len(atual)} cursos em 2026; abaixo de 1 na média 2024-2026: {(atual.cv < 1).sum()}")
    for coluna in ["local", "cidade", "grau", "turno", "area"]:
        print("\n--", coluna); print(taxa_por_grupo(atual, coluna).to_string())
    print("\n-- regressão (efeito em % sobre cand/vaga, comparado a Curitiba, integral, bacharelado, saúde)")
    regressao(atual)
    print("\n-- decomposição 2017 -> 2026"); decompor(s)
    print("\n-- oferta total"); oferta_total()
    print("\n-- os 25 cursos com menos candidatos por vaga")
    print(atual.sort_values("cv").head(25)[["cv", "vagas"]].round(2).to_string())
