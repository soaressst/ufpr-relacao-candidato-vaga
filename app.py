import streamlit as st
import pandas as pd

from pipeline.db import engine

# 1. Configuração da Página
st.set_page_config(page_title="Simulador UFPR", layout="wide")
st.title("🎓 Simulador Preditivo de Concorrência - UFPR")
st.markdown("MVP para simulação de impacto exógeno na relação Candidato/Vaga (2026).")

# 3. Carregando os Dados
# Recarrega do banco a cada hora, para refletir novas cargas do etl_ingestao sem reiniciar o app
@st.cache_data(ttl=3600)
def carregar_dados():
    query = """
        SELECT curso, campus, cand_vaga_2026,
               prev_2027, faixa_2027_min, faixa_2027_max, prob_sobra_2027, risco_2027
        FROM ufpr_analytics.vw_powerbi_concorrencia
        ORDER BY cand_vaga_2026 DESC
    """
    return pd.read_sql(query, engine)

df = carregar_dados()

# 4. Interface Lateral (Parâmetros What-If)
st.sidebar.header("⚙️ Parâmetros de Simulação")
st.sidebar.markdown("Ajuste as variáveis macroeconômicas para simular o impacto na demanda.")

fator_impacto = st.sidebar.slider(
    "Choque Geral (Renda/Emprego) (%)", 
    min_value=-30.0, 
    max_value=30.0, 
    value=0.0, 
    step=5.0
)

# 5. Processamento da Simulação
# Recalcula a coluna baseada no slider
df['Cenário Simulado'] = df['cand_vaga_2026'] * (1 + (fator_impacto / 100))

# 6. Exibição Visual (Gráfico e Tabela)
st.subheader(f"Comparativo de Cenários (Fator: {fator_impacto}%)")

# Preparar dados para o gráfico de barras
df_grafico = df.head(15).set_index("curso")[['cand_vaga_2026', 'Cenário Simulado']]
df_grafico = df_grafico.rename(columns={'cand_vaga_2026': 'Cenário Base'})

# Barras lado a lado (empilhadas somariam os dois cenários)
st.bar_chart(df_grafico, stack=False)

st.divider()

# 7. Risco de sobra de vagas em 2027
# Faixas validadas com a ocupação oficial das vagas 2016-2022: abaixo de 1 candidato por vaga o curso
# terminou com vaga sobrando em 100% dos casos; de 1 a 1,5, em 57%.
st.subheader("⚠️ Risco de sobra de vagas no Vestibular 2027")
ordem_risco = ["Sobra certa", "Risco alto", "Atenção", "Baixo"]
contagem = df["risco_2027"].value_counts()
for coluna, nivel in zip(st.columns(4), ordem_risco):
    coluna.metric(nivel, int(contagem.get(nivel, 0)))
st.caption(
    "Candidatos por vaga previstos para 2027, contra as vagas de referência (antes dos cortes de 2025). "
    "Sobra certa: abaixo de 1 · Risco alto: 1 a 1,5 · Atenção: 1,5 a 2 · Baixo: 2 ou mais. "
    "A faixa cobre 80% dos erros reais do modelo um ano à frente."
)
em_risco = df[df["risco_2027"] != "Baixo"].sort_values("prev_2027")
st.dataframe(
    em_risco[["curso", "campus", "risco_2027", "prev_2027", "faixa_2027_min", "faixa_2027_max", "prob_sobra_2027"]].rename(columns={
        "curso": "Curso", "campus": "Campus", "risco_2027": "Risco", "prev_2027": "Previsão 2027",
        "faixa_2027_min": "Faixa mín.", "faixa_2027_max": "Faixa máx.", "prob_sobra_2027": "Prob. de sobra",
    }),
    column_config={"Prob. de sobra": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)},
    hide_index=True,
    width="stretch",
)

st.divider()

st.subheader("📊 Tabela Detalhada")
st.dataframe(
    df.style.highlight_max(subset=['Cenário Simulado'], color='lightgreen'),
    width="stretch"
)