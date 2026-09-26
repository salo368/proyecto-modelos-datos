-- Creates the data warehouse database next to the metadata repository.
--
-- The PostgreSQL instance starts with the 'metadata' database (POSTGRES_DB
-- in docker-compose.yml); this script adds 'dw' on the same server.

CREATE DATABASE dw;

COMMENT ON DATABASE dw IS
    'Almacen de datos dimensional: constelacion con fact_ventas y '
    'fact_llamadas_servicio unidos por dimensiones conformadas.';
