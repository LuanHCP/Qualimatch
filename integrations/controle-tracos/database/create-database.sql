-- Execute conectado ao banco padrão "postgres".
-- Depois conecte-se ao novo banco e rode database/setup.sql.
CREATE DATABASE tracos_teste
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    TEMPLATE = template0;
