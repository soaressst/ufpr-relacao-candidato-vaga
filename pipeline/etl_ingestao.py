import os
import pandas as pd
from sqlalchemy import text

from pipeline.db import engine, RAIZ

# Substitui as previsões no banco pelo CSV de data/gold, numa única transação:
# se qualquer passo falhar, nada é apagado nem gravado.

TURNOS = {"M": "Matutino", "N": "Noturno", "V": "Vespertino", "T": "Vespertino"}


def turno(curso):
    # O turno é o último trecho do nome: "... - PR - N", "... - PR - I (M+V)"
    return TURNOS.get(curso.rsplit(" - ", 1)[-1].strip(), "Integral")


def grau(curso):
    if "Licenciatura/Bacharelado" in curso:
        return "Licenciatura/Bacharelado"
    if "Bacharelado" in curso:
        return "Bacharelado"
    if "Licenciatura" in curso:
        return "Licenciatura"
    return "Tecnológico"


print("--- 1. Conectando ao PostgreSQL na Nuvem (Supabase) ---")

# 2. Carregar o arquivo CSV (camada gold)
df_csv = pd.read_csv(os.path.join(RAIZ, "data", "gold", "UFPR_Previsao_Concorrencia_Por_Curso_2027_2032.csv"))
df_csv["Ano_Entrada_Sobra_Vagas"] = df_csv["Ano_Entrada_Sobra_Vagas"].astype(str)
print(f"-> CSV lido com sucesso: {len(df_csv)} linhas encontradas.")

# Contexto de conexão com gerenciamento automático de transação
with engine.begin() as conn:
    # Apaga a carga anterior (fato antes das dimensões); sem CASCADE para não atingir outras tabelas
    for tabela in ["fato_previsao_concorrencia", "dim_curso", "dim_campus"]:
        apagadas = conn.execute(text(f"DELETE FROM ufpr_analytics.{tabela}")).rowcount
        print(f"-> {tabela}: {apagadas} linhas antigas removidas.")

    # 3. Dimensão Curso
    df_cursos = df_csv[['Curso']].drop_duplicates().rename(columns={'Curso': 'nome_curso'})
    df_cursos['turno'] = df_cursos['nome_curso'].apply(turno)
    df_cursos['grau'] = df_cursos['nome_curso'].apply(grau)
    df_cursos.to_sql('dim_curso', conn, schema='ufpr_analytics', if_exists='append', index=False)
    print(f"-> Dimensão 'dim_curso' gravada! ({len(df_cursos)} linhas)")

    # 4. Dimensão Campus
    df_campus = df_csv[['Campus']].drop_duplicates().rename(columns={'Campus': 'nome_campus'})
    df_campus.to_sql('dim_campus', conn, schema='ufpr_analytics', if_exists='append', index=False)
    print(f"-> Dimensão 'dim_campus' gravada! ({len(df_campus)} linhas)")

    # 5. Tabela Fato (o CSV tem colunas extras, como as vagas de referência, que a tabela não tem).
    # As colunas de 2027 exigem sql/002_risco_2027.sql aplicado no banco.
    colunas_fato = {
        'Curso': 'nome_curso',
        'Campus': 'nome_campus',
        'Cand_Vaga_2026': 'cand_vaga_2026',
        'Ano_Minimo': 'ano_minimo',
        'Valor_Minimo': 'valor_minimo',
        'Ano_Entrada_Sobra_Vagas': 'ano_entrada_sobra_vagas',
        'Prev_2027': 'prev_2027',
        'Faixa_2027_Min': 'faixa_2027_min',
        'Faixa_2027_Max': 'faixa_2027_max',
        'Prob_Sobra_2027': 'prob_sobra_2027',
        'Risco_2027': 'risco_2027',
    }
    df_fato = df_csv[list(colunas_fato)].rename(columns=colunas_fato)
    df_fato.to_sql('fato_previsao_concorrencia', conn, schema='ufpr_analytics', if_exists='append', index=False)
    print(f"-> Tabela Fato 'fato_previsao_concorrencia' gravada! ({len(df_fato)} linhas)")

print("\n--- INGESTÃO CONCLUÍDA COM SUCESSO! ---")
