"""
Build the Metabase dashboard through Metabase's REST API.

  1. Create the admin user on a fresh instance, or log in.
  2. Remove Metabase's bundled sample database and dashboards.
  3. Register the data warehouse ('dw') as the only data source.
  4. Create or update one native-SQL question per report. Every query
     reads the warehouse, never the original sources.
  5. Create the dashboard with the six cards (two per row).

Requires Metabase running (docker compose up -d metabase).

Usage:
    python reports/build_dashboard.py
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

METABASE_URL = os.getenv("METABASE_URL", "http://localhost:3000")
API = METABASE_URL + "/api"
ADMIN = {
    "first_name": "Grupo",
    "last_name": "Javeriana",
    "email": "grupo@javeriana.edu.co",
    "password": "Javeriana2026!",
}
DATA_SOURCE_NAME = "Almacen de Datos"
DASHBOARD_NAME = "Entrega 2 - Almacen Ventas y Servicio"

DW_URL = os.getenv("DW_URL")   # postgresql+psycopg2://user:pass@host:port/dw

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def split_url(url):
    """host, port, user, password and database of a SQLAlchemy URL."""
    rest = url.split("://", 1)[1]
    credentials, server = rest.rsplit("@", 1)
    user, password = credentials.split(":", 1)
    host_port, database = server.split("/", 1)
    host, port = host_port.split(":")
    return host, int(port), user, password, database


def metabase_connection():
    """Connection details as seen from inside the Metabase container.

    When the warehouse runs in the same docker-compose stack, the .env
    URL points to localhost and the published port (5434), which is not
    reachable from inside the container; the compose service name and
    internal port are used instead. A remote warehouse is used as-is,
    with SSL enabled.
    """
    host, port, user, password, database = split_url(DW_URL)

    if host in LOCAL_HOSTS:
        internal_host = os.getenv("DW_HOST_DOCKER", "postgres-dw")
        internal_port = int(os.getenv("DW_PORT_DOCKER", "5432"))
        print(f"  Local warehouse: Metabase reaches it as "
              f"{internal_host}:{internal_port} inside the Docker network.")
        return internal_host, internal_port, user, password, database, False

    return host, port, user, password, database, True


# ============================================================
# Reports: name and description are shown in Metabase.
# ============================================================

REPORTS = [
    {
        "name": "Ventas y margen por mes",
        "description": "Evolucion mensual del monto vendido y el margen bruto. "
                       "Solo ordenes efectivas: excluye Cancelled, Disputed y On Hold.",
        "display": "combo",
        "sql": """
SELECT t.anio_mes                       AS mes,
       ROUND(SUM(f.monto_linea),  2)    AS monto_vendido,
       ROUND(SUM(f.margen_linea), 2)    AS margen
FROM fact_ventas f
JOIN dim_tiempo       t ON f.tiempo_key = t.tiempo_key
JOIN dim_estado_orden e ON f.estado_key = e.estado_key
WHERE e.es_efectiva
GROUP BY t.anio_mes
ORDER BY t.anio_mes
""",
        "viz": {"graph.dimensions": ["mes"],
                "graph.metrics": ["monto_vendido", "margen"]},
    },
    {
        "name": "Intensidad de servicio por producto",
        "description": "Llamadas al centro de servicio por unidad vendida en "
                       "ordenes efectivas. Cruza los dos hechos del almacen: es "
                       "la pregunta que ninguna de las dos fuentes responde por "
                       "si sola.",
        "display": "bar",
        "sql": """
SELECT nombre_producto                  AS producto,
       ROUND(SUM(num_llamadas)::numeric
             / NULLIF(SUM(unidades_vendidas), 0), 4) AS llamadas_por_unidad
FROM dm.vw_interaccion_cliente_producto
GROUP BY nombre_producto
HAVING SUM(unidades_vendidas) > 0
   AND SUM(num_llamadas)      > 0
ORDER BY llamadas_por_unidad DESC
LIMIT 12
""",
        "viz": {"graph.dimensions": ["producto"],
                "graph.metrics": ["llamadas_por_unidad"]},
    },
    {
        "name": "Margen por linea de producto",
        "description": "Monto vendido y margen bruto de cada linea del catalogo.",
        "display": "row",
        "sql": """
SELECT p.linea_producto               AS linea,
       ROUND(SUM(f.monto_linea), 2)   AS monto_vendido,
       ROUND(SUM(f.margen_linea), 2)  AS margen
FROM fact_ventas f
JOIN dim_producto p ON f.producto_key = p.producto_key
GROUP BY p.linea_producto
ORDER BY monto_vendido DESC
""",
        "viz": {"graph.dimensions": ["linea"],
                "graph.metrics": ["monto_vendido", "margen"]},
    },
    {
        "name": "Clientes: compras frente a llamadas",
        "description": "Cada punto es un cliente. Eje X lo que compro en "
                       "ordenes efectivas, eje Y cuantas veces llamo al centro "
                       "de servicio.",
        "display": "scatter",
        "sql": """
SELECT nombre_cliente                   AS cliente,
       ROUND(SUM(monto_vendido), 2)     AS monto_comprado,
       SUM(num_llamadas)                AS llamadas
FROM dm.vw_interaccion_cliente_producto
GROUP BY nombre_cliente
HAVING SUM(monto_vendido) > 0
ORDER BY monto_comprado DESC
""",
        "viz": {"graph.dimensions": ["monto_comprado"],
                "graph.metrics": ["llamadas"]},
    },
    {
        "name": "Ventas por oficina",
        "description": "Monto vendido segun la oficina del representante "
                       "de ventas asignado al cliente.",
        "display": "bar",
        "sql": """
SELECT o.ciudad || ' (' || o.pais || ')'  AS oficina,
       ROUND(SUM(f.monto_linea), 2)       AS monto_vendido
FROM fact_ventas f
JOIN dim_oficina o ON f.oficina_key = o.oficina_key
GROUP BY o.ciudad, o.pais
ORDER BY monto_vendido DESC
""",
        "viz": {"graph.dimensions": ["oficina"],
                "graph.metrics": ["monto_vendido"]},
    },
    {
        "name": "Carga del centro de servicio por agente",
        "description": "Llamadas atendidas por cada agente de customerservice. "
                       "La llave compuesta de dim_empleado garantiza que los "
                       "vendedores de classicmodels no aparezcan aqui.",
        "display": "table",
        "sql": """
SELECT e.nombre || ' ' || e.apellido  AS agente,
       e.sistema_origen               AS sistema,
       COUNT(*)                       AS llamadas_atendidas,
       ROUND(AVG(l.longitud_texto))   AS longitud_promedio_nota
FROM fact_llamadas_servicio l
JOIN dim_empleado e ON l.empleado_key = e.empleado_key
GROUP BY e.nombre, e.apellido, e.sistema_origen
ORDER BY llamadas_atendidas DESC
LIMIT 15
""",
        "viz": {},
    },
]


# ============================================================
# Metabase API client
# ============================================================

class Metabase:
    def __init__(self):
        self.session = requests.Session()

    def get(self, path, **kw):
        r = self.session.get(API + path, timeout=60, **kw)
        r.raise_for_status()
        return r.json()

    def post(self, path, payload):
        r = self.session.post(API + path, json=payload, timeout=120)
        if not r.ok:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    def put(self, path, payload):
        r = self.session.put(API + path, json=payload, timeout=120)
        if not r.ok:
            raise RuntimeError(f"PUT {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    def authenticate(self):
        """Create the admin user on a fresh instance; otherwise log in."""
        token = self.get("/session/properties").get("setup-token")
        if token:
            print("  Fresh instance: creating the admin user...")
            self.post("/setup", {
                "token": token,
                "user": ADMIN,
                "prefs": {"site_name": "Javeriana - Entrega 2",
                          "site_locale": "es"},
                "database": None,
            })
            print(f"  Admin created: {ADMIN['email']}")
        else:
            self.post("/session", {"username": ADMIN["email"],
                                   "password": ADMIN["password"]})
            print("  Logged in.")

    def register_warehouse(self):
        host, port, user, password, database, ssl = metabase_connection()

        for d in self.get("/database").get("data", []):
            if d["name"] == DATA_SOURCE_NAME:
                print(f"  Data source already registered (id={d['id']}).")
                return d["id"]

        d = self.post("/database", {
            "name": DATA_SOURCE_NAME,
            "engine": "postgres",
            "details": {
                "host": host, "port": port, "dbname": database,
                "user": user, "password": password,
                "ssl": ssl, "tunnel-enabled": False,
            },
        })
        print(f"  Warehouse registered (id={d['id']}).")
        return d["id"]

    def remove_samples(self):
        """Delete the bundled Sample Database and archive other dashboards."""
        removed = False
        for d in self.get("/database").get("data", []):
            if d.get("is_sample") or d["name"] == "Sample Database":
                r = self.session.delete(API + f"/database/{d['id']}", timeout=120)
                print(f"  Sample Database {'deleted' if r.ok else 'could not be deleted'}.")
                removed = True
        if not removed:
            print("  No Sample Database present.")

        for d in self.get("/dashboard"):
            if d["name"] != DASHBOARD_NAME:
                self.put(f"/dashboard/{d['id']}", {"archived": True})
                print(f"  Archived sample dashboard: {d['name']}")

    def wait_for_sync(self, db_id, attempts=30):
        """Metabase discovers tables in the background."""
        for _ in range(attempts):
            try:
                tables = self.get(f"/database/{db_id}/metadata").get("tables", [])
                if len(tables) >= 8:
                    print(f"  Schema synced: {len(tables)} tables.")
                    return
            except Exception:
                pass
            time.sleep(5)
        print("  Warning: schema sync is slow; native SQL questions work anyway.")


# ============================================================
# Build
# ============================================================

def main():
    mb = Metabase()

    print("Connecting to Metabase...")
    mb.authenticate()

    print("Removing sample content...")
    mb.remove_samples()

    print("Registering the warehouse as data source...")
    db_id = mb.register_warehouse()
    mb.wait_for_sync(db_id)

    print("Creating or updating questions...")
    existing = {c["name"]: c["id"] for c in mb.get("/card")}
    card_ids = []
    for r in REPORTS:
        definition = {
            "name": r["name"],
            "description": r["description"],
            "display": r["display"],
            "dataset_query": {
                "type": "native",
                "native": {"query": r["sql"].strip()},
                "database": db_id,
            },
            "visualization_settings": r["viz"],
        }
        if r["name"] in existing:
            card_id = existing[r["name"]]
            mb.put(f"/card/{card_id}", definition)
            print(f"  updated: {r['name']}")
        else:
            card_id = mb.post("/card", definition)["id"]
            print(f"  created: {r['name']}")
        card_ids.append(card_id)

    print("Building the dashboard...")
    dashboard = next((d for d in mb.get("/dashboard") if d["name"] == DASHBOARD_NAME), None)
    if dashboard:
        dashboard_id = dashboard["id"]
        print(f"  already exists: {DASHBOARD_NAME}")
    else:
        dashboard_id = mb.post("/dashboard", {
            "name": DASHBOARD_NAME,
            "description": "Reportes sobre el almacen dimensional. Todas las "
                           "consultas van contra la base 'dw'; ninguna toca "
                           "classicmodels ni customerservice.",
        })["id"]

        # Two cards per row, 12 grid columns each.
        dashcards = [{
            "id": -(i + 1),
            "card_id": card_id,
            "row": (i // 2) * 8,
            "col": (i % 2) * 12,
            "size_x": 12,
            "size_y": 8,
        } for i, card_id in enumerate(card_ids)]
        mb.put(f"/dashboard/{dashboard_id}", {"dashcards": dashcards})
        print(f"  created with {len(dashcards)} cards.")

    print()
    print("Done.")
    print(f"  Dashboard : {METABASE_URL}/dashboard/{dashboard_id}")
    print(f"  User      : {ADMIN['email']}")
    print(f"  Password  : {ADMIN['password']}")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        sys.exit(f"Cannot reach {METABASE_URL}. Is the container up? (docker ps)")
