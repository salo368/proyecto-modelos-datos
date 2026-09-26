-- Creates the data warehouse and the staging area next to the metadata
-- repository.
--
-- The PostgreSQL instance starts with the 'metadata' database (POSTGRES_DB
-- in docker-compose.yml); this script adds, on the same server:
--
--   dw       the data warehouse: EDW (public) and data marts (dm)
--   staging  the staging area of the pipeline (layers 1-6), kept out
--            of the warehouse
--
-- On a volume created before 'staging' existed, run_all.py creates it
-- (tools/create_database.py).

CREATE DATABASE dw;

COMMENT ON DATABASE dw IS
    'Almacen de datos dimensional: constelacion con fact_ventas y '
    'fact_llamadas_servicio unidos por dimensiones conformadas.';

CREATE DATABASE staging;

COMMENT ON DATABASE staging IS
    'Area de staging del pipeline: una tabla por capa de la arquitectura de '
    'integracion de Giordano. No es parte del almacen.';
