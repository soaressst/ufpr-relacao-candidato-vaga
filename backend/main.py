from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from pipeline.db import engine

app = FastAPI(title="UFPR Analytics API", version="1.0")

# Habilitar CORS para permitir que o frontend acesse a API localmente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/cursos")
def listar_cursos(fator_impacto: float = Query(0.0, description="Percentual de choque exógeno ex: 0.15 para +15%")):
    """
    Retorna a lista de cursos com a concorrência base de 2026 
    e o valor recalculado com base no fator de impacto exógeno.
    """
    query = """
        SELECT curso, campus, turno, grau, cand_vaga_2026, ano_entrada_sobra_vagas, valor_minimo
        FROM ufpr_analytics.vw_powerbi_concorrencia
        ORDER BY cand_vaga_2026 DESC
    """
    df = pd.read_sql(query, engine)
    
    # Aplica o cálculo de simulação no DataFrame
    df['cand_vaga_simulada'] = df['cand_vaga_2026'] * (1 + fator_impacto)
    df['cand_vaga_simulada'] = df['cand_vaga_simulada'].round(2)
    
    # Converte o DataFrame para lista de dicionários (JSON)
    return df.to_dict(orient="records")

@app.get("/api/kpis")
def obter_kpis(fator_impacto: float = Query(0.0)):
    """
    Retorna os KPIs gerais do sistema.
    """
    query = "SELECT COUNT(*) as total_cursos FROM ufpr_analytics.dim_curso"
    df_cursos = pd.read_sql(query, engine)
    
    query_risco = """
        SELECT COUNT(*) as cursos_risco 
        FROM ufpr_analytics.vw_powerbi_concorrencia 
        WHERE ano_entrada_sobra_vagas <> 'Sem Sobra'
    """
    df_risco = pd.read_sql(query_risco, engine)
    
    total = int(df_cursos['total_cursos'].iloc[0])
    risco = int(df_risco['cursos_risco'].iloc[0])
    taxa_risco = round((risco / total) * 100, 1) if total > 0 else 0.0

    return {
        "total_cursos": total,
        "cursos_com_risco": risco,
        "taxa_risco_institucional": f"{taxa_risco}%"
    }