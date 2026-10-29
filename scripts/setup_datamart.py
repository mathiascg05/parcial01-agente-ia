"""
Crea y carga el Data Mart ejecutando sql/Datamart.sql (sin necesidad de psql) y concilia contra la fuente.

  python scripts/setup_datamart.py              # usa PG_ADMIN_USER / PG_ADMIN_PASSWORD de .env
  python scripts/setup_datamart.py --crear-db   # además crea la base de datos si no existe

Pasos: (1) ejecuta el script SQL (las líneas \\copy se ejecutan como COPY FROM STDIN),
(2) define la contraseña del rol agente_lector desde PG_PASSWORD, (3) muestra las vistas de control y
(4) hace una conciliación INDEPENDIENTE con pandas leyendo directamente los CSV de la fuente.
Guarda el resultado en docs/evidencias/conciliacion.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402
import psycopg  # noqa: E402
from psycopg import sql as psql  # noqa: E402

from agente.config import CONFIG  # noqa: E402

COPY_RE = re.compile(r"^\\copy\s+(\S+)(\s*\([^)]*\))?\s+FROM\s+'([^']+)'\s+WITH\s+\((.+)\)\s*$", re.I)


def crear_db():
    dsn = CONFIG.dsn(admin=True).replace(f"dbname={CONFIG.pg_db}", "dbname=postgres")
    with psycopg.connect(dsn, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (CONFIG.pg_db,)).fetchone():
            c.execute(psql.SQL("CREATE DATABASE {}").format(psql.Identifier(CONFIG.pg_db)))
            print(f"Base de datos {CONFIG.pg_db} creada")


def ejecutar_script(conn, ruta: Path):
    bloque: list[str] = []

    def vaciar():
        texto = "\n".join(bloque).strip()
        bloque.clear()
        if texto:
            conn.execute(texto)

    for linea in ruta.read_text(encoding="utf-8").splitlines():
        m = COPY_RE.match(linea.strip())
        if m:
            vaciar()
            tabla, columnas, archivo, opciones = m.group(1), m.group(2) or "", m.group(3), m.group(4)
            with conn.cursor() as cur:
                with cur.copy(f"COPY {tabla}{columnas} FROM STDIN WITH ({opciones})") as cp:
                    cp.write((RAIZ / archivo).read_bytes())
            print(f"  COPY {tabla} <- {archivo}")
        else:
            bloque.append(linea)
    vaciar()


def conciliacion_independiente() -> dict:
    """Recalcula los totales leyendo los CSV con pandas (sin pasar por PostgreSQL)."""
    f = RAIZ / "data" / "fuente"
    t = pd.read_csv(f / "tickets.csv", dtype=str, keep_default_na=False)
    d = pd.read_csv(f / "ticket_detalle.csv")
    d = d.drop_duplicates(subset=["ticket_id", "linea"], keep="first")
    d = d.merge(t[["ticket_id", "estado"]], on="ticket_id")
    d = d[(d.estado == "COMPLETADO") & (d.cantidad > 0)]
    ingreso = (d.cantidad * d.precio_unitario - d.descuento).round(2).sum()
    return {"lineas": int(len(d)), "tickets": int(d.ticket_id.nunique()), "unidades": int(d.cantidad.sum()),
            "ingreso_neto": round(float(ingreso), 2), "costo": round(float((d.cantidad * d.costo_unitario).sum()), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crear-db", action="store_true")
    a = ap.parse_args()
    if a.crear_db:
        crear_db()
    print(f"Ejecutando sql/Datamart.sql en {CONFIG.pg_db} como {CONFIG.pg_admin_user} ...")
    with psycopg.connect(CONFIG.dsn(admin=True), autocommit=True) as conn:
        ejecutar_script(conn, RAIZ / "sql" / "Datamart.sql")
        if CONFIG.pg_password:
            conn.execute(psql.SQL("ALTER ROLE agente_lector PASSWORD {}").format(psql.Literal(CONFIG.pg_password)))
            print("  Contraseña de agente_lector definida desde PG_PASSWORD (.env)")
        conc = conn.execute("SELECT control, valor_fuente, valor_dm, diferencia, estado FROM control.v_conciliacion_estado").fetchall()
        integ = conn.execute("SELECT control, hallazgos FROM control.v_integridad ORDER BY substring(control from 2 for 2)::INT").fetchall()
        exc = conn.execute("SELECT dimension, miembro, lineas, tickets, ingreso_neto, pct_ingreso FROM control.v_excepciones").fetchall()
        dm = conn.execute("SELECT COUNT(*), COUNT(DISTINCT numero_ticket), SUM(cantidad), SUM(ingreso_neto), SUM(costo_total) "
                          "FROM dm.fact_ventas").fetchone()

    print("\nCONCILIACIÓN Data Mart vs fuente operacional (SQL):")
    for c in conc:
        print(f"  [{c[4]}] {c[0]}: fuente={c[1]} dm={c[2]} dif={c[3]}")
    print("\nINTEGRIDAD:")
    for c in integ:
        print(f"  [{'OK' if c[1] == 0 else 'REVISAR'}] {c[0]}: {c[1]}")
    ind = conciliacion_independiente()
    dm_d = {"lineas": dm[0], "tickets": dm[1], "unidades": int(dm[2]), "ingreso_neto": float(dm[3]), "costo": float(dm[4])}
    print("\nCONCILIACIÓN INDEPENDIENTE (pandas sobre CSV vs Data Mart):")
    filas_ind = []
    for k in ind:
        ok = abs(ind[k] - dm_d[k]) < 0.005
        filas_ind.append({"control": k, "csv": ind[k], "dm": dm_d[k], "estado": "OK" if ok else "REVISAR"})
        print(f"  [{'OK' if ok else 'REVISAR'}] {k}: csv={ind[k]} dm={dm_d[k]}")
    salida = RAIZ / "docs" / "evidencias"
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "conciliacion.json").write_text(json.dumps({
        "conciliacion_sql": [dict(zip(["control", "valor_fuente", "valor_dm", "diferencia", "estado"], map(str, c))) for c in conc],
        "integridad": [{"control": c[0], "hallazgos": c[1]} for c in integ],
        "excepciones": [dict(zip(["dimension", "miembro", "lineas", "tickets", "ingreso_neto", "pct_ingreso"], map(str, e))) for e in exc],
        "conciliacion_independiente": filas_ind}, ensure_ascii=False, indent=2), encoding="utf-8")
    todo_ok = all(c[4] == "OK" for c in conc) and all(c[1] == 0 for c in integ) and all(f["estado"] == "OK" for f in filas_ind)
    print(f"\nResultado global: {'TODO OK' if todo_ok else 'HAY CONTROLES PARA REVISAR'}  (docs/evidencias/conciliacion.json)")
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
