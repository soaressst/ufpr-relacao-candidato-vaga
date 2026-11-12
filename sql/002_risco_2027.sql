-- Acrescenta a previsão de 2027 com faixa de incerteza, probabilidade de sobra e classe de risco.
-- Só ACRESCENTA colunas (não apaga nem altera dados). As colunas novas ficam vazias até o etl_ingestao.
-- A view é recriada com as mesmas 8 colunas de antes, na mesma ordem, e as 5 novas no final
-- (o Postgres só permite CREATE OR REPLACE VIEW acrescentando colunas no fim).

ALTER TABLE ufpr_analytics.fato_previsao_concorrencia
    ADD COLUMN IF NOT EXISTS prev_2027       double precision,
    ADD COLUMN IF NOT EXISTS faixa_2027_min  double precision,
    ADD COLUMN IF NOT EXISTS faixa_2027_max  double precision,
    ADD COLUMN IF NOT EXISTS prob_sobra_2027 double precision,
    ADD COLUMN IF NOT EXISTS risco_2027      text;

CREATE OR REPLACE VIEW ufpr_analytics.vw_powerbi_concorrencia AS
SELECT f.nome_curso AS curso, c.turno, c.grau, f.nome_campus AS campus,
       f.cand_vaga_2026, f.ano_minimo, f.valor_minimo, f.ano_entrada_sobra_vagas,
       f.prev_2027, f.faixa_2027_min, f.faixa_2027_max, f.prob_sobra_2027, f.risco_2027
FROM ufpr_analytics.fato_previsao_concorrencia f
LEFT JOIN ufpr_analytics.dim_curso c ON f.nome_curso::text = c.nome_curso::text
LEFT JOIN ufpr_analytics.dim_campus cp ON f.nome_campus::text = cp.nome_campus::text;
