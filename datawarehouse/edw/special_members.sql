-- ============================================================
-- Special members of the dimensions
--
-- A fact points to one of these rows instead of carrying a NULL
-- foreign key, so every join keeps every fact and a report shows why
-- the member is missing:
--
--   -1  Desconocido  the source names a member that did not reach the
--                    warehouse: it does not exist, or Data Quality
--                    rejected it
--   -2  Sin asignar  the source leaves the reference empty
--
-- Only the dimensions a fact may leave unresolved have them: the sales
-- rep of fact_ventas (dim_empleado) and the rep's office (dim_oficina).
-- Every other reference is mandatory, and the pipeline rejects a record
-- whose parent is missing instead.
--
-- Negative surrogate keys never collide with the SERIAL ones, and the
-- load upserts on the business key, so it never touches these rows.
-- Idempotent. Run after star_schema.sql.
-- ============================================================

INSERT INTO dim_empleado (empleado_key, numero_empleado, sistema_origen, nombre,
                          apellido, email, cargo, numero_oficina)
VALUES (-1, -1, 'N/A', 'Desconocido', 'N/A', 'N/A', 'Desconocido', 'N/A'),
       (-2, -2, 'N/A', 'Sin asignar', 'N/A', 'N/A', 'Sin asignar', 'N/A')
ON CONFLICT (empleado_key) DO UPDATE
    SET numero_empleado = EXCLUDED.numero_empleado,
        sistema_origen  = EXCLUDED.sistema_origen,
        nombre          = EXCLUDED.nombre,
        apellido        = EXCLUDED.apellido,
        email           = EXCLUDED.email,
        cargo           = EXCLUDED.cargo,
        numero_oficina  = EXCLUDED.numero_oficina;

INSERT INTO dim_oficina (oficina_key, codigo_oficina, ciudad, pais, region, territorio)
VALUES (-1, '-1', 'Desconocida', 'N/A', 'N/A', 'N/A'),
       (-2, '-2', 'Sin asignar', 'N/A', 'N/A', 'N/A')
ON CONFLICT (oficina_key) DO UPDATE
    SET codigo_oficina = EXCLUDED.codigo_oficina,
        ciudad         = EXCLUDED.ciudad,
        pais           = EXCLUDED.pais,
        region         = EXCLUDED.region,
        territorio     = EXCLUDED.territorio;
