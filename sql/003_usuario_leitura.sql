-- 003: usuário só de leitura para o app (Streamlit) e a API.
-- Rodar no SQL Editor do Supabase como administrador. Pode rodar de novo sem erro.
-- A senha NÃO fica neste arquivo: defina depois, direto no SQL Editor (passo 2 abaixo).

-- 1. Cria o usuário (sem senha = ainda não consegue entrar)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'leitor_app') THEN
        CREATE ROLE leitor_app LOGIN NOINHERIT;
    END IF;
END
$$;

-- Toda transação desse usuário é só leitura, mesmo que alguém tente gravar
ALTER ROLE leitor_app SET default_transaction_read_only = on;
-- Consulta travada não segura conexão do plano free
ALTER ROLE leitor_app SET statement_timeout = '15s';

-- Só enxerga o schema do projeto
GRANT USAGE ON SCHEMA ufpr_analytics TO leitor_app;
GRANT SELECT ON ALL TABLES IN SCHEMA ufpr_analytics TO leitor_app;   -- inclui a view

-- Tabelas e views que o administrador criar depois também ficam legíveis
ALTER DEFAULT PRIVILEGES IN SCHEMA ufpr_analytics GRANT SELECT ON TABLES TO leitor_app;

-- 2. Senha: rode SEPARADO, com uma senha forte gerada por você, e não salve em arquivo:
--    ALTER ROLE leitor_app PASSWORD '...';

-- 3. Conferência (deve listar só SELECT)
-- SELECT table_name, privilege_type
-- FROM information_schema.role_table_grants
-- WHERE grantee = 'leitor_app' ORDER BY 1;
