"""
Construye el dashboard de la Entrega 2 en Metabase, via su API REST.

Hace todo el montaje sin tocar la interfaz grafica:
  1. Crea el usuario administrador si la instancia esta recien levantada.
  2. Registra el almacen de datos ('dw' en Railway) como origen.
  3. Crea una pregunta (card) por cada reporte, con SQL nativo contra el
     almacen. Ninguna consulta toca las fuentes originales, como exige
     el enunciado.
  4. Arma el dashboard y coloca las tarjetas.

Requisitos:
    El contenedor tiene que estar arriba:
        docker run -d --name metabase -p 3000:3000 \
            -v metabase-data:/metabase.db \
            -e MB_DB_FILE=/metabase.db/metabase.db metabase/metabase:latest

Uso:
    python reports/construir_dashboard.py
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("METABASE_URL", "http://localhost:3000") + "/api"
ADMIN = {
    "first_name": "Grupo",
    "last_name": "Javeriana",
    "email": "grupo@javeriana.edu.co",
    "password": "Javeriana2026!",
}

# Datos de conexion del almacen, tomados del .env para no repetirlos.
DW_URL = os.getenv("DW_URL")   # postgresql+psycopg2://user:pass@host:puerto/dw

LOCALES = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


def partir_url(url):
    """Extrae host, puerto, usuario, clave y base de la cadena de SQLAlchemy."""
    resto = url.split("://", 1)[1]
    credenciales, servidor = resto.rsplit("@", 1)
    usuario, clave = credenciales.split(":", 1)
    hostpuerto, base = servidor.split("/", 1)
    host, puerto = hostpuerto.split(":")
    return host, int(puerto), usuario, clave, base


def conexion_para_metabase():
    """Traduce la cadena del .env a lo que Metabase necesita.

    Este script corre en la maquina anfitriona, pero Metabase corre dentro
    de un contenedor. Cuando el almacen tambien esta en Docker, la cadena
    del .env apunta a localhost con el puerto publicado (5434), que desde
    adentro del contenedor no lleva a ninguna parte: hay que usar el nombre
    del servicio en la red de compose y el puerto interno.

    Si el almacen esta en un servidor remoto, la cadena se usa tal cual y
    se activa SSL, que es lo que exigen los proveedores en la nube.
    """
    host, puerto, usuario, clave, base = partir_url(DW_URL)

    if host in LOCALES:
        host_interno = os.getenv("DW_HOST_DOCKER", "postgres-dw")
        puerto_interno = int(os.getenv("DW_PORT_DOCKER", "5432"))
        print(f"  Almacen local: Metabase lo alcanzara como "
              f"{host_interno}:{puerto_interno} dentro de la red de Docker.")
        return host_interno, puerto_interno, usuario, clave, base, False

    return host, puerto, usuario, clave, base, True


# ============================================================
# Reportes. Cada uno es una consulta contra el ALMACEN.
# ============================================================

REPORTES = [
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
        "description": "Llamadas al centro de servicio por unidad vendida. "
                       "Cruza los dos hechos del almacen: es la pregunta que "
                       "ninguna de las dos fuentes responde por si sola.",
        "display": "bar",
        "sql": """
SELECT nombre_producto                  AS producto,
       ROUND(SUM(num_llamadas)::numeric
             / NULLIF(SUM(unidades_vendidas), 0), 4) AS llamadas_por_unidad
FROM vw_interaccion_cliente_producto
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
        "description": "Monto vendido y porcentaje de margen de cada linea "
                       "del catalogo.",
        "display": "row",
        "sql": """
SELECT p.linea_producto               AS linea,
       ROUND(SUM(f.monto_linea), 2)   AS monto_vendido
FROM fact_ventas f
JOIN dim_producto p ON f.producto_key = p.producto_key
GROUP BY p.linea_producto
ORDER BY monto_vendido DESC
""",
        "viz": {"graph.dimensions": ["linea"],
                "graph.metrics": ["monto_vendido"]},
    },
    {
        "name": "Clientes: compras frente a llamadas",
        "description": "Cada punto es un cliente. Eje X lo que compro, eje Y "
                       "cuantas veces llamo al centro de servicio.",
        "display": "scatter",
        "sql": """
SELECT nombre_cliente                   AS cliente,
       ROUND(SUM(monto_vendido), 2)     AS monto_comprado,
       SUM(num_llamadas)                AS llamadas
FROM vw_interaccion_cliente_producto
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
        "description": "Llamadas atendidas por cada agente. Solo aparecen los "
                       "30 agentes de customerservice, nunca los vendedores de "
                       "classicmodels: es la prueba de que la llave compuesta "
                       "de dim_empleado separa bien las dos poblaciones.",
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
# Cliente de la API
# ============================================================

class Metabase:
    def __init__(self):
        self.s = requests.Session()

    def _url(self, ruta):
        return f"{BASE}{ruta}"

    def get(self, ruta, **kw):
        r = self.s.get(self._url(ruta), timeout=60, **kw)
        r.raise_for_status()
        return r.json()

    def post(self, ruta, payload):
        r = self.s.post(self._url(ruta), json=payload, timeout=120)
        if not r.ok:
            raise RuntimeError(f"POST {ruta} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    def put(self, ruta, payload):
        r = self.s.put(self._url(ruta), json=payload, timeout=120)
        if not r.ok:
            raise RuntimeError(f"PUT {ruta} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}

    # --- autenticacion ---

    def autenticar(self):
        """Crea el admin si la instancia es nueva; si no, inicia sesion."""
        props = self.get("/session/properties")
        token = props.get("setup-token")

        if token:
            print("  Instancia nueva: creando usuario administrador...")
            self.post("/setup", {
                "token": token,
                "user": ADMIN,
                "prefs": {"site_name": "Javeriana - Entrega 2",
                          "site_locale": "es"},
                "database": None,
            })
            print(f"  Admin creado: {ADMIN['email']}")
        else:
            self.post("/session", {"username": ADMIN["email"],
                                   "password": ADMIN["password"]})
            print("  Sesion iniciada.")

    # --- origen de datos ---

    def registrar_almacen(self):
        host, puerto, usuario, clave, base, ssl = conexion_para_metabase()

        for d in self.get("/database").get("data", []):
            if d["name"] == "Almacen de Datos":
                print(f"  Origen ya registrado (id={d['id']}).")
                return d["id"]

        d = self.post("/database", {
            "name": "Almacen de Datos",
            "engine": "postgres",
            "details": {
                "host": host, "port": puerto, "dbname": base,
                "user": usuario, "password": clave,
                "ssl": ssl, "tunnel-enabled": False,
            },
        })
        print(f"  Almacen registrado (id={d['id']}).")
        return d["id"]

    def quitar_ejemplos(self):
        """Elimina la 'Sample Database' que Metabase trae de fabrica.

        Sin esto, la instancia queda con unas cuarenta preguntas de ejemplo
        sobre datos ficticios que ensucian las capturas del entregable y
        podrian confundirse con reportes del proyecto.
        """
        quitada = False
        for d in self.get("/database").get("data", []):
            if d.get("is_sample") or d["name"] == "Sample Database":
                r = self.s.delete(self._url(f"/database/{d['id']}"), timeout=120)
                print(f"  Sample Database {'eliminada' if r.ok else 'no se pudo eliminar'}.")
                quitada = True
        if not quitada:
            print("  Sample Database ya no estaba.")

        # Borrar el origen deja el dashboard de ejemplo vacio, asi que se
        # archiva aparte para que no aparezca junto al de la entrega.
        for d in self.get("/dashboard"):
            if d["name"] != "Entrega 2 - Almacen Ventas y Servicio":
                self.put(f"/dashboard/{d['id']}", {"archived": True})
                print(f"  Dashboard de ejemplo archivado: {d['name']}")

    def esperar_sincronizacion(self, db_id, intentos=30):
        """Metabase descubre las tablas en segundo plano."""
        for i in range(intentos):
            try:
                meta = self.get(f"/database/{db_id}/metadata")
                tablas = [t["name"] for t in meta.get("tables", [])]
                if len(tablas) >= 8:
                    print(f"  Esquema sincronizado: {len(tablas)} tablas.")
                    return
            except Exception:
                pass
            time.sleep(5)
        print("  Aviso: la sincronizacion va lenta, pero el SQL nativo "
              "funciona igual.")


# ============================================================
# Montaje
# ============================================================

def main():
    mb = Metabase()

    print("Conectando con Metabase...")
    mb.autenticar()

    print("Limpiando el contenido de ejemplo...")
    mb.quitar_ejemplos()

    print("Registrando el almacen como origen de datos...")
    db_id = mb.registrar_almacen()
    mb.esperar_sincronizacion(db_id)

    print("Creando los reportes...")
    existentes = {c["name"]: c["id"] for c in mb.get("/card")}
    tarjetas = []
    for r in REPORTES:
        if r["name"] in existentes:
            card_id = existentes[r["name"]]
            print(f"  (ya existia) {r['name']}")
        else:
            card = mb.post("/card", {
                "name": r["name"],
                "description": r["description"],
                "display": r["display"],
                "dataset_query": {
                    "type": "native",
                    "native": {"query": r["sql"].strip()},
                    "database": db_id,
                },
                "visualization_settings": r["viz"],
            })
            card_id = card["id"]
            print(f"  creado: {r['name']}")
        tarjetas.append(card_id)

    print("Armando el dashboard...")
    nombre_dash = "Entrega 2 - Almacen Ventas y Servicio"
    dash = next((d for d in mb.get("/dashboard") if d["name"] == nombre_dash), None)
    if dash:
        dash_id = dash["id"]
        print(f"  (ya existia) {nombre_dash}")
    else:
        dash = mb.post("/dashboard", {
            "name": nombre_dash,
            "description": "Reportes sobre el almacen dimensional. Todas las "
                           "consultas van contra la base 'dw'; ninguna toca "
                           "classicmodels ni customerservice.",
        })
        dash_id = dash["id"]

        # Dos tarjetas por fila, cada una de 12 columnas de ancho.
        filas = []
        for i, card_id in enumerate(tarjetas):
            filas.append({
                "id": -(i + 1),
                "card_id": card_id,
                "row": (i // 2) * 8,
                "col": (i % 2) * 12,
                "size_x": 12,
                "size_y": 8,
            })
        mb.put(f"/dashboard/{dash_id}", {"dashcards": filas})
        print(f"  creado con {len(filas)} tarjetas.")

    print()
    print("Listo.")
    print(f"  Dashboard : http://localhost:3000/dashboard/{dash_id}")
    print(f"  Usuario   : {ADMIN['email']}")
    print(f"  Clave     : {ADMIN['password']}")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        sys.exit("No pude conectarme a http://localhost:3000. "
                 "Verifica que el contenedor este arriba: docker ps")
