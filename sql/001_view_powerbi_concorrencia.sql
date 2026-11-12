-- View lida pelo app (Streamlit), pela API e pelo Power BI.
-- Criada no SQL Editor do Supabase em 29/10/2026 (registro do que já está no banco).
CREATE OR REPLACE VIEW ufpr_analytics.vw_powerbi_concorrencia AS
SELECT f.nome_curso AS curso, c.turno, c.grau, f.nome_campus AS campus,
       f.cand_vaga_2026, f.ano_minimo, f.valor_minimo, f.ano_entrada_sobra_vagas
FROM ufpr_analytics.fato_previsao_concorrencia f
LEFT JOIN ufpr_analytics.dim_curso c ON f.nome_curso::text = c.nome_curso::text
LEFT JOIN ufpr_analytics.dim_campus cp ON f.nome_campus::text = cp.nome_campus::text;
