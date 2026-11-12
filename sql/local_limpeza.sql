-- Limpeza do Postgres LOCAL (localhost:5432, base postgres, schema ufpr_analytics).
-- NÃO é para o Supabase. Rodar no DBeaver, conectado ao banco local.
--
-- Desde 29/10/2026 o app, a API e o Power BI leem o Supabase; nada depende mais do banco local.
-- Estas tabelas guardam dados que não devem ser usados:
--   fato_historico_concorrencia  -> 7 cursos inventados pelo antigo scraping_nc_ufpr.py (removido)
--   fato_previsao_historico_log  -> registros do antigo modelo Ridge (R² = 0)
--   dim_indicadores_demograficos -> séries escritas à mão no antigo etl_ibge.py (só o IPCA vinha de API)
--   fato_previsao_concorrencia / dim_curso / dim_campus / vw_powerbi_concorrencia -> previsões antigas (Holt)
--
-- ANTES DE RODAR: faça um backup. No DBeaver: botão direito no schema ufpr_analytics ->
-- Ferramentas -> Backup (ou exportar as tabelas para CSV). DROP não tem volta.
--
-- Opção A (recomendada): apagar o schema inteiro. O histórico e as previsões corretas estão no
-- repositório (data/gold) e no Supabase.

BEGIN;
DROP SCHEMA IF EXISTS ufpr_analytics CASCADE;
COMMIT;

-- Opção B: manter o schema e apagar só os dados inventados/obsoletos (comente a Opção A acima
-- e descomente o bloco abaixo).
--
-- BEGIN;
-- DROP TABLE IF EXISTS ufpr_analytics.fato_historico_concorrencia;
-- DROP TABLE IF EXISTS ufpr_analytics.fato_previsao_historico_log;
-- DROP TABLE IF EXISTS ufpr_analytics.dim_indicadores_demograficos;
-- COMMIT;
