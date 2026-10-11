-- Migration inicial (versão base do Flyway).
-- Novas migrations: migrations/V<AAAAMMDDHHMM>__descricao.sql
-- Nunca edite uma migration já aplicada; crie uma nova.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
