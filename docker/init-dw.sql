-- Crea la base del almacen de datos junto a la del repositorio de metadatos.
--
-- La instancia de PostgreSQL arranca con la base 'metadata' (definida en
-- POSTGRES_DB del docker-compose). Este script agrega la base 'dw' al lado,
-- replicando la misma topologia que se uso en Railway: dos bases separadas
-- dentro de un mismo servidor, para no pagar un servicio adicional.

CREATE DATABASE dw;

COMMENT ON DATABASE dw IS
    'Almacen de datos dimensional - Entrega 2. Constelacion con fact_ventas '
    'y fact_llamadas_servicio unidos por dimensiones conformadas.';
