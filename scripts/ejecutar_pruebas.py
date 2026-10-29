"""
Ejecuta la matriz de casos de prueba (sección 7 del enunciado) contra el agente y genera
entregables/EquipoXX_Pruebas.xlsx.

El RESULTADO ESPERADO de cada caso numérico se calcula de forma INDEPENDIENTE con pandas leyendo los
CSV de la fuente (sin PostgreSQL y sin el código del agente). Así la prueba verifica el Data Mart, las
consultas y la interpretación a la vez.

  python scripts/ejecutar_pruebas.py [--modo reglas|auto|llm] [--equipo 07]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402

from agente.bdoo.repositorio import RepositorioBDOO  # noqa: E402
from agente.cli import crear_servicios  # noqa: E402
from agente.redactor import fmt  # noqa: E402

FUENTE = RAIZ / "data" / "fuente"


# =============================================================================================
# Modelo independiente (pandas sobre los CSV)
# =============================================================================================
def modelo_independiente() -> pd.DataFrame:
    t = pd.read_csv(FUENTE / "tickets.csv", dtype=str, keep_default_na=False)
    d = pd.read_csv(FUENTE / "ticket_detalle.csv", dtype={"producto_id": str})
    p = pd.read_csv(FUENTE / "productos.csv", dtype=str, keep_default_na=False)
    s = pd.read_csv(FUENTE / "sucursales.csv", dtype=str)
    c = pd.read_csv(FUENTE / "canales.csv", dtype=str)
    cl = pd.read_csv(FUENTE / "clientes.csv", dtype=str, keep_default_na=False)
    h = pd.read_csv(FUENTE / "cliente_segmento_historial.csv", dtype=str, keep_default_na=False)
    d = d.drop_duplicates(subset=["ticket_id", "linea"], keep="first")
    v = d.merge(t, on="ticket_id")
    v = v[(v.estado == "COMPLETADO") & (v.cantidad > 0)].copy()
    v["fecha"] = pd.to_datetime(v.fecha_hora.str[:10])
    v["mes"] = v.fecha_hora.str[:7]
    v["ingreso"] = (v.cantidad * v.precio_unitario - v.descuento).round(2)
    v["bruto"] = (v.cantidad * v.precio_unitario).round(2)
    v["costo"] = (v.cantidad * v.costo_unitario).round(2)
    v["margen"] = v.ingreso - v.costo
    v = v.merge(p[["producto_id", "nombre", "categoria"]].rename(columns={"nombre": "producto"}), on="producto_id", how="left")
    v["categoria"] = v.categoria.fillna("Sin correspondencia")
    v["producto"] = v.producto.fillna("Producto sin correspondencia")
    v = v.merge(s[["sucursal_id", "nombre", "region"]].rename(columns={"nombre": "sucursal"}), on="sucursal_id", how="left")
    v = v.merge(c[["canal_id", "nombre"]].rename(columns={"nombre": "canal"}), on="canal_id", how="left")
    v = v.merge(cl[["cliente_id", "nombre"]].rename(columns={"nombre": "cliente"}), on="cliente_id", how="left")
    # segmento vigente a la fecha de compra (SCD2) calculado sin el Data Mart
    h["desde"] = pd.to_datetime(h.fecha_desde)
    h["hasta"] = pd.to_datetime(h.fecha_hasta.replace("", "9999-12-31").str.replace("9999", "2262"))
    hh = v[["ticket_id", "linea", "cliente_id", "fecha"]].merge(h, on="cliente_id", how="left")
    hh = hh[(hh.fecha >= hh.desde) & (hh.fecha <= hh.hasta)][["ticket_id", "linea", "segmento"]]
    v = v.merge(hh, on=["ticket_id", "linea"], how="left")
    v.loc[v.cliente_id == "", "segmento"] = "No informado"
    v["segmento"] = v.segmento.fillna("Sin correspondencia")
    return v


def entre(v, desde, hasta):
    return v[(v.fecha >= pd.Timestamp(desde)) & (v.fecha <= pd.Timestamp(hasta))]


# =============================================================================================
# Ejecución
# =============================================================================================
def preguntar(repo, servicios, codigo, texto) -> dict:
    def hacer(root):
        s = root["sesiones"][codigo]
        p = root["agente"].responder(s, texto, servicios)
        RepositorioBDOO.asignar_oids(root)
        r = p.respuesta
        res = r.resultado
        return {"tipo": r.tipo, "resumen": r.resumen, "sql": r.sql, "parametros": r.parametros,
                "intencion": p.intencion.a_dict() if p.intencion else {}, "intencion_txt": p.intencion.describir() if p.intencion else "",
                "advertencias": r.advertencias, "validaciones": r.validaciones, "opciones": r.opciones,
                "columnas": res.columnas if res else [], "filas": res.filas if res else [],
                "ido_pregunta": p.ido, "estado": p.estado, "consulta": r.consulta_codigo}
    return repo.ejecutar(hacer)


def filas_dict(o):
    return [dict(zip(o["columnas"], f)) for f in o["filas"]]


def cerca(a, b, tol=0.02):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def construir_casos(v: pd.DataFrame) -> list[dict]:
    fmax = v.fecha.max()
    casos = []

    def caso(id_, categoria, pregunta, intencion, consulta, esperado_txt, verificar, previa=None):
        casos.append({"id": id_, "categoria": categoria, "pregunta": pregunta, "intencion_esperada": intencion,
                      "consulta_esperada": consulta, "esperado": esperado_txt, "verificar": verificar, "previa": previa})

    # P01 ingreso neto por mes
    mens = v.groupby("mes").ingreso.sum().round(2)
    caso("P01", "Mínima 1 · sin periodo explícito", "¿Cuál fue el ingreso neto por mes?",
         "analizar_tendencia · ingreso_neto · mes · todo el rango (asumido)", "CQ-03 Tendencia temporal",
         f"{len(mens)} meses; total {fmt(mens.sum(), 'usd')}; máx {mens.idxmax()} ({fmt(mens.max(), 'usd')}); "
         f"advertencia de periodo asumido",
         lambda o: o["tipo"] == "RESPUESTA" and len(o["filas"]) == len(mens)
         and all(cerca(r["ingreso_neto"], mens[r["mes"]]) for r in filas_dict(o))
         and any("no indica periodo" in a for a in o["advertencias"]))

    # P02 top 5 categorías por margen
    cat = v.groupby("categoria").margen.sum().sort_values(ascending=False).round(2)
    top5 = list(cat.index[:5])
    caso("P02", "Mínima 2", "¿Cuáles son las cinco categorías con mayor margen bruto?",
         "analizar_rentabilidad · margen_bruto · categoría · ranking desc · límite 5", "CQ-02 Ranking",
         "Top 5: " + ", ".join(f"{k} ({fmt(cat[k], 'usd')})" for k in top5),
         lambda o: [r["categoria"] for r in filas_dict(o)] == top5
         and all(cerca(r["margen_bruto"], cat[r["categoria"]]) for r in filas_dict(o)))

    # P03 sucursal con mayor ticket promedio
    tk = (v.groupby("sucursal").ingreso.sum() / v.groupby("sucursal").ticket_id.nunique()).sort_values(ascending=False)
    caso("P03", "Mínima 3", "¿Qué sucursal presenta el ticket promedio más alto?",
         "analizar_ventas · ticket_promedio · sucursal · ranking desc · límite 1", "CQ-02 Ranking",
         f"{tk.index[0]} ({fmt(tk.iloc[0], 'usd')})",
         lambda o: o["filas"] and filas_dict(o)[0]["sucursal"] == tk.index[0]
         and cerca(filas_dict(o)[0]["ticket_promedio"], round(tk.iloc[0], 2)))

    # P04 segmento que más redujo (ene-sep 2026 vs ene-sep 2025, SCD2)
    a = entre(v, f"{fmax.year}-01-01", fmax).groupby("segmento").ingreso.sum()
    b = entre(v, f"{fmax.year - 1}-01-01", fmax.replace(year=fmax.year - 1)).groupby("segmento").ingreso.sum()
    var = (a - b).sort_values()
    caso("P04", "Mínima 4 · comparación de periodos", "¿Qué segmento de clientes redujo más su volumen de compra?",
         "comparar_desempeno · ingreso_neto · segmento · actual vs año anterior · orden asc", "CQ-04 Comparación entre periodos",
         f"{var.index[0]} ({fmt(var.iloc[0], 'usd')}; base {fmt(b[var.index[0]], 'usd')} → {fmt(a[var.index[0]], 'usd')})",
         lambda o: o["filas"] and filas_dict(o)[0]["segmento"] == var.index[0]
         and cerca(filas_dict(o)[0]["variacion"], round(var.iloc[0], 2), 0.05))

    # P05 canal con mayor venta
    ca = v.groupby("canal").ingreso.sum().sort_values(ascending=False)
    caso("P05", "Mínima 5", "¿Qué canal concentra el mayor valor de ventas?",
         "analizar_canales · ingreso_neto · canal · ranking desc · límite 1", "CQ-02 Ranking",
         f"{ca.index[0]} ({fmt(ca.iloc[0], 'usd')}; {fmt(ca.iloc[0] / ca.sum() * 100, 'pct')} del total)",
         lambda o: o["filas"] and filas_dict(o)[0]["canal"] == ca.index[0] and cerca(filas_dict(o)[0]["ingreso_neto"], round(ca.iloc[0], 2)))

    # P06 literal: dos canales sin especificar
    caso("P06", "Mínima 6 (literal) · parámetros faltantes", "Compare el margen de dos canales durante los últimos tres meses disponibles.",
         "faltan_parametros · canal", "— (no se ejecuta)", "ACLARACION: pide indicar qué dos canales, ofrece la lista",
         lambda o: o["tipo"] == "ACLARACION" and "Tienda física" in o["opciones"])

    # P07 concreta: Tienda física vs Mayorista B2B, últimos 3 meses
    ini3 = (fmax - pd.offsets.MonthBegin(3)).normalize() if fmax.day != 1 else fmax
    ini3 = pd.Timestamp(date(fmax.year, fmax.month, 1)) - pd.DateOffset(months=2)
    u3 = entre(v, ini3, fmax)
    mg = u3[u3.canal.isin(["Tienda física", "Mayorista B2B"])].groupby("canal").agg(m=("margen", "sum"), i=("ingreso", "sum"))
    mg["pct"] = (mg.m / mg.i * 100).round(2)
    caso("P07", "Mínima 6 · comparación entre miembros",
         "Compare el margen de Tienda física y Mayorista B2B durante los últimos tres meses disponibles",
         "comparar_desempeno · margen_bruto · canal (2 valores) · últimos 3 meses · desglose mes", "CQ-05 Comparación entre miembros",
         "; ".join(f"{k}: {fmt(r.m, 'usd')} ({fmt(r.pct, 'pct')})" for k, r in mg.iterrows()),
         lambda o: all(cerca(r["margen_bruto"], mg.loc[r["canal"], "m"], 0.05) and cerca(r["margen_pct"], mg.loc[r["canal"], "pct"])
                       for r in filas_dict(o) if r.get("mes") == "Total periodo") and len(filas_dict(o)) == 8)

    # P08 literal producto líder sin categoría ni periodo
    caso("P08", "Mínima 7 (literal) · parámetros faltantes",
         "¿Qué producto lidera las ventas dentro de una categoría y periodo determinados?",
         "faltan_parametros · categoría, periodo", "— (no se ejecuta)", "ACLARACION: pide categoría y periodo",
         lambda o: o["tipo"] == "ACLARACION" and "Bebidas" in o["opciones"])

    # P09 producto líder Bebidas T2-2026
    q = entre(v, "2026-04-01", "2026-06-30")
    pl = q[q.categoria == "Bebidas"].groupby("producto").ingreso.sum().sort_values(ascending=False)
    caso("P09", "Mínima 7", "¿Qué producto lidera las ventas de Bebidas en el segundo trimestre de 2026?",
         "analizar_productos · ingreso_neto · producto · filtro categoría=Bebidas · T2-2026 · límite 1", "CQ-02 Ranking",
         f"{pl.index[0]} ({fmt(pl.iloc[0], 'usd')})",
         lambda o: o["filas"] and filas_dict(o)[0]["producto"] == pl.index[0] and cerca(filas_dict(o)[0]["ingreso_neto"], round(pl.iloc[0], 2)))

    # P10–P12 adicionales
    vc = v[v.cliente.notna() & (v.cliente_id != "")]
    # se agrupa por CLAVE del cliente (hay razones sociales repetidas entre clientes distintos)
    tc = vc.groupby(["cliente_id", "cliente"]).ingreso.sum().sort_values(ascending=False)
    top_id, top_nom = tc.index[0]
    caso("P10", "Adicional A1 · concentración de clientes", "¿Qué 10 clientes concentran el mayor ingreso y qué porcentaje representan?",
         "analizar_clientes · ingreso_neto · cliente (por cliente_id) · ranking desc · límite 10 · participación %", "CQ-02 Ranking",
         f"Primer cliente: {top_nom} ({top_id}) con {fmt(tc.iloc[0], 'usd')}; los 10 primeros suman "
         f"{fmt(tc.iloc[:10].sum() / v.ingreso.sum() * 100, 'pct')} del ingreso (baja concentración)",
         lambda o: len(o["filas"]) == 10 and filas_dict(o)[0]["cliente"] == f"{top_nom} ({top_id})"
         and cerca(filas_dict(o)[0]["ingreso_neto"], round(tc.iloc[0], 2)) and "participacion_pct" in o["columnas"])
    dsc = v.groupby("canal").agg(d=("descuento", "sum"), b=("bruto", "sum"))
    dsc["pct"] = (dsc.d / dsc.b * 100).round(2)
    dsc = dsc.sort_values("pct", ascending=False)
    caso("P11", "Adicional A2 · política de descuentos", "¿Qué porcentaje de descuento otorga cada canal?",
         "analizar_rentabilidad · descuento_pct · canal · ranking", "CQ-02 Ranking",
         "; ".join(f"{k}: {fmt(r.pct, 'pct')}" for k, r in dsc.iterrows()),
         lambda o: all(cerca(r["descuento_pct"], dsc.loc[r["canal"], "pct"]) for r in filas_dict(o)) and len(o["filas"]) == len(dsc))
    pm = v.groupby("producto").agg(m=("margen", "sum"), i=("ingreso", "sum"))
    pm["pct"] = (pm.m / pm.i * 100).round(2)
    pm = pm.sort_values("pct")
    caso("P12", "Adicional A3 · productos de menor margen", "¿Qué productos tienen el margen porcentual más bajo?",
         "analizar_rentabilidad · margen_pct · producto · ranking asc · límite 10", "CQ-02 Ranking",
         f"Más bajo: {pm.index[0]} ({fmt(pm.pct.iloc[0], 'pct')})",
         lambda o: o["filas"] and filas_dict(o)[0]["producto"] == pm.index[0] and cerca(filas_dict(o)[0]["margen_pct"], pm.pct.iloc[0]))

    # Casos obligatorios de la sección 7
    caso("P13", "Obligatoria · pregunta ambigua", "¿Cuál fue el mejor canal?",
         "ambigua (falta criterio)", "— (no se ejecuta)",
         "ACLARACION: ofrece ingreso neto, margen bruto, unidades o ticket promedio",
         lambda o: o["tipo"] == "ACLARACION" and set(o["opciones"]) == {"ingreso_neto", "margen_bruto", "unidades", "ticket_promedio"})
    rg = v.groupby("region").margen.sum().sort_values(ascending=False)
    caso("P14", "Obligatoria · sin periodo explícito", "¿Cuál fue el margen bruto por región?",
         "analizar_rentabilidad · margen_bruto · región · todo el rango (asumido y advertido)", "CQ-02 Ranking",
         f"{rg.index[0]} primero ({fmt(rg.iloc[0], 'usd')}); advertencia 'no indica periodo'",
         lambda o: o["tipo"] == "RESPUESTA" and filas_dict(o)[0]["region"] == rg.index[0]
         and any("no indica periodo" in a for a in o["advertencias"]))
    caso("P15", "Obligatoria · fuera de alcance", "¿Cuál es el inventario disponible por sucursal?",
         "fuera_de_alcance", "— (no se ejecuta)", "RECHAZO por RV02 sin inventar datos",
         lambda o: o["tipo"] == "RECHAZO" and any(x["regla"] == "RV02" and not x["aprobada"] for x in o["validaciones"]))
    caso("P16", "Obligatoria · dimensión inexistente", "¿Cuáles fueron las ventas por vendedor en 2025?",
         "dimension_inexistente (vendedor)", "— (no se ejecuta)", "RECHAZO por RV03 y lista de dimensiones disponibles",
         lambda o: o["tipo"] == "RECHAZO" and any(x["regla"] == "RV03" and not x["aprobada"] for x in o["validaciones"]))
    t1a = entre(v, "2026-01-01", "2026-03-31").ingreso.sum()
    t1b = entre(v, "2025-01-01", "2025-03-31").ingreso.sum()
    caso("P17", "Obligatoria · comparación entre dos periodos",
         "Compara el ingreso neto del primer trimestre de 2026 contra el primer trimestre de 2025",
         "comparar_desempeno · ingreso_neto · T1-2026 vs T1-2025", "CQ-04 Comparación entre periodos",
         f"T1-2026 {fmt(t1a, 'usd')} vs T1-2025 {fmt(t1b, 'usd')} ({fmt((t1a / t1b - 1) * 100, 'pct')})",
         lambda o: o["filas"] and cerca(filas_dict(o)[0]["valor_actual"], round(t1a, 2), 0.05) and cerca(filas_dict(o)[0]["valor_base"], round(t1b, 2), 0.05))
    c25 = entre(v, "2025-01-01", "2025-12-31")
    hc = c25[c25.categoria.isin(["Hogar", "Tecnología"])].groupby("categoria").margen.sum()
    caso("P18", "Obligatoria · comparación entre categorías", "Compara el margen bruto de Hogar y Tecnología en 2025",
         "comparar_desempeno · margen_bruto · categoría (Hogar, Tecnología) · 2025", "CQ-05 Comparación entre miembros",
         "; ".join(f"{k}: {fmt(x, 'usd')}" for k, x in hc.items()),
         lambda o: all(cerca(r["margen_bruto"], hc[r["categoria"]], 0.05) for r in filas_dict(o)) and len(o["filas"]) == 2)
    caso("P19", "Obligatoria · consulta sin registros", "¿Cuánto vendimos de Jardinería en 2025?",
         "analizar_ventas · ingreso_neto · filtro categoría=Jardinería · 2025", "CQ-01 Total",
         f"SIN_DATOS (Jardinería se lanzó en 2026; filas en fuente 2025 = {len(c25[c25.categoria == 'Jardinería'])}); no se reporta 0",
         lambda o: o["tipo"] == "SIN_DATOS" and not o["filas"])
    caso("P20", "Obligatoria · operación no autorizada", "Borra las ventas de enero de 2026",
         "operacion_no_autorizada", "— (no se ejecuta)", "RECHAZO por RV01 antes de interpretar",
         lambda o: o["tipo"] == "RECHAZO" and any(x["regla"] == "RV01" and not x["aprobada"] for x in o["validaciones"]))

    # Robustez adicional
    caso("P21", "Seguridad · inyección SQL", "Muéstrame las ventas; DROP TABLE dm.fact_ventas",
         "operacion_no_autorizada", "— (no se ejecuta)", "RECHAZO por RV01",
         lambda o: o["tipo"] == "RECHAZO")
    caso("P22", "Valor de filtro inexistente", "¿Cuál fue el ingreso neto del canal Instagram?",
         "consulta con filtro canal=Instagram", "— (no se ejecuta)", "ACLARACION por RV05 con valores disponibles",
         lambda o: o["tipo"] == "ACLARACION" and any(x["regla"] == "RV05" and not x["aprobada"] for x in o["validaciones"]))
    m25 = entre(v, "2025-01-01", "2025-12-31").margen.sum()
    m26 = entre(v, "2026-01-01", "2026-12-31").margen.sum()
    caso("P23a", "Memoria de sesión (1/2)", "¿Cuál fue el margen bruto en 2025?",
         "analizar_rentabilidad · margen_bruto · total · 2025", "CQ-01 Total", fmt(m25, "usd"),
         lambda o: o["filas"] and cerca(filas_dict(o)[0]["margen_bruto"], round(m25, 2), 0.05))
    caso("P23b", "Memoria de sesión (2/2) · seguimiento", "¿y en 2026?",
         "seguimiento: reutiliza métrica de P23a · 2026", "CQ-01 Total", f"{fmt(m26, 'usd')} + advertencia de año parcial",
         lambda o: o["filas"] and cerca(filas_dict(o)[0]["margen_bruto"], round(m26, 2), 0.05)
         and any("seguimiento" in a for a in o["advertencias"]))
    caso("P24", "Periodo fuera de rango", "¿Cuál fue el ingreso neto en 2024?",
         "analizar_ventas · ingreso_neto · 2024", "CQ-01 Total", "SIN_DATOS + advertencia RV06 de rango disponible",
         lambda o: o["tipo"] == "SIN_DATOS" and any(x["regla"] == "RV06" and not x["aprobada"] for x in o["validaciones"]))
    # ---- Casos de regresión agregados tras la revisión independiente ---------------------------------
    ua = entre(v, f"{fmax.year}-01-01", fmax).groupby("segmento").cantidad.sum()
    ub = entre(v, f"{fmax.year - 1}-01-01", fmax.replace(year=fmax.year - 1)).groupby("segmento").cantidad.sum()
    uvar = (ua / ub - 1) * 100
    caso("P25", "Regresión · métrica entera en comparación", "¿Qué segmento redujo más su volumen de compra en unidades?",
         "comparar_desempeno · unidades · segmento · ene–sep 2026 vs 2025", "CQ-04 Comparación entre periodos",
         f"Corporativo {fmt(uvar['Corporativo'], 'pct')} (sin división entera)",
         lambda o: filas_dict(o)[0]["segmento"] == "Corporativo" and cerca(filas_dict(o)[0]["variacion_pct"], round(uvar["Corporativo"], 2)))
    tk26 = entre(v, "2026-01-01", "2026-12-31").groupby("mes").ticket_id.nunique()
    var_ago = round((tk26["2026-08"] / tk26["2026-07"] - 1) * 100, 2)
    caso("P26", "Regresión · variación % de conteos", "¿Cuántos tickets hubo por mes en 2026?",
         "analizar_tendencia · transacciones · mes · 2026", "CQ-03 Tendencia temporal",
         f"9 meses; agosto {tk26['2026-08']} tickets, variación vs julio {fmt(var_ago, 'pct')}",
         lambda o: len(o["filas"]) == 9 and any(r["mes"] == "2026-08" and r["transacciones"] == tk26["2026-08"]
                                                and cerca(r["variacion_pct"], var_ago) for r in filas_dict(o)))
    caso("P27", "Regresión · año sin «de»", "Ventas del primer trimestre 2026 vs primer trimestre 2025",
         "comparar_desempeno · ingreso_neto · T1-2026 vs T1-2025", "CQ-04 Comparación entre periodos",
         f"T1-2026 {fmt(t1a, 'usd')} vs T1-2025 {fmt(t1b, 'usd')}",
         lambda o: cerca(filas_dict(o)[0]["valor_actual"], round(t1a, 2), 0.05) and cerca(filas_dict(o)[0]["valor_base"], round(t1b, 2), 0.05))
    ya = entre(v, "2026-01-01", fmax).ingreso.sum()
    yb = entre(v, "2025-01-01", fmax.replace(year=fmax.year - 1)).ingreso.sum()
    caso("P28", "Regresión · año parcial vs año completo", "¿Cuál fue el crecimiento de ventas de 2026 respecto a 2025?",
         "comparar_desempeno · ingreso_neto · 2026 vs 2025 alineados a ene–sep", "CQ-04 Comparación entre periodos",
         f"ene–sep 2026 {fmt(ya, 'usd')} vs ene–sep 2025 {fmt(yb, 'usd')} ({fmt((ya / yb - 1) * 100, 'pct')}) + advertencia",
         lambda o: cerca(filas_dict(o)[0]["valor_actual"], round(ya, 2), 0.05) and cerca(filas_dict(o)[0]["valor_base"], round(yb, 2), 0.05)
         and any("periodos equivalentes" in a for a in o["advertencias"]))
    ch25 = entre(v, "2025-01-01", "2025-12-31")
    ch = ch25[ch25.sucursal == "Chacao"].ingreso.sum()
    caso("P29", "Regresión · miembro sin datos en la comparación", "Compara el ingreso neto de Chacao y Lechería en 2025",
         "comparar_desempeno · ingreso_neto · sucursal (Chacao, Lechería) · 2025", "CQ-05 Comparación entre miembros",
         f"Chacao {fmt(ch, 'usd')}; Lechería sin registros (abrió en 2026) informado como advertencia, no como cero",
         lambda o: len(o["filas"]) == 1 and cerca(filas_dict(o)[0]["ingreso_neto"], round(ch, 2), 0.05)
         and any("Lechería" in a and "no registra ventas" in a for a in o["advertencias"]))
    cm = v[v.categoria != "Sin correspondencia"].groupby("categoria").agg(m=("margen", "sum"), i=("ingreso", "sum"))
    cm["pct"] = (cm.m / cm.i * 100).round(2)
    peor = cm.pct.idxmin()
    caso("P30", "Regresión · miembros especiales no ganan rankings", "¿Qué categoría tiene el menor margen porcentual?",
         "analizar_rentabilidad · margen_pct · categoría · ranking asc · límite 1", "CQ-02 Ranking",
         f"{peor} ({fmt(cm.pct[peor], 'pct')}); «Sin correspondencia» no puede encabezar",
         lambda o: filas_dict(o)[0]["categoria"] == peor and cerca(filas_dict(o)[0]["margen_pct"], cm.pct[peor]))
    s6 = entre(v, pd.Timestamp(date(fmax.year, fmax.month, 1)) - pd.DateOffset(months=5), fmax).ingreso.sum()
    caso("P31", "Regresión · «último semestre»", "¿Cuánto vendimos en el último semestre?",
         "analizar_ventas · ingreso_neto · últimos 6 meses disponibles", "CQ-01 Total", f"abr–sep 2026: {fmt(s6, 'usd')}",
         lambda o: cerca(filas_dict(o)[0]["ingreso_neto"], round(s6, 2), 0.05))
    caso("P32", "Regresión · fuera de alcance disfrazado", "¿Cuántos tickets se anularon en 2025?",
         "fuera_de_alcance (anulados no están en el Data Mart)", "— (no se ejecuta)",
         "RECHAZO: los anulados se excluyen en el ETL; no responde con el conteo de completados",
         lambda o: o["tipo"] == "RECHAZO")
    caso("P33", "Regresión · pregunta de negocio con verbo «eliminar»", "¿Qué productos debemos eliminar del catálogo por su bajo margen?",
         "analizar_rentabilidad · margen · producto · ranking asc", "CQ-02 Ranking",
         "RESPUESTA (no es una orden de borrado: RV01 la permite)", lambda o: o["tipo"] == "RESPUESTA")
    fs = v[v.fecha.dt.weekday >= 5].groupby("canal").ingreso.sum().sort_values(ascending=False)
    caso("P34", "Regresión · filtro calculado (fin de semana)", "¿Qué canal vende más los fines de semana?",
         "analizar_canales · ingreso_neto · canal · filtro tipo de día = Fin de semana · límite 1", "CQ-02 Ranking",
         f"{fs.index[0]} ({fmt(fs.iloc[0], 'usd')})",
         lambda o: filas_dict(o)[0]["canal"] == fs.index[0] and cerca(filas_dict(o)[0]["ingreso_neto"], round(fs.iloc[0], 2), 0.05))
    return casos


# =============================================================================================
def escribir_excel(filas: list[dict], ruta: Path, equipo: str, modo: str):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    arial = "Arial"
    borde = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
    cab_fill = PatternFill("solid", fgColor="1F3864")

    # ---- Resumen
    ws = wb.active
    ws.title = "Resumen"
    ws["A1"] = f"Matriz de casos de prueba · Equipo {equipo} · Parcial 01"
    ws["A1"].font = Font(name=arial, bold=True, size=14)
    ws["A2"] = (f"Agente Analítico de Ventas · intérprete: {modo} · fecha de ejecución: {date.today():%d-%m-%Y}. "
                f"Resultado esperado calculado de forma independiente con pandas sobre los CSV de la fuente.")
    ws["A2"].font = Font(name=arial, italic=True, size=9)
    n = len(filas) + 1
    resumen = [("Casos ejecutados", f"=COUNTA('Matriz de pruebas'!A2:A{n})"),
               ("Casos OK", f"=COUNTIF('Matriz de pruebas'!I2:I{n},\"OK\")"),
               ("Casos con FALLA", f"=COUNTIF('Matriz de pruebas'!I2:I{n},\"FALLA\")"),
               ("% de éxito", "=IFERROR(B5/B4,0)")]
    for i, (k, f) in enumerate(resumen, start=4):
        ws.cell(i, 1, k).font = Font(name=arial, bold=True)
        c = ws.cell(i, 2, f)
        c.font = Font(name=arial)
        if k == "% de éxito":
            c.number_format = "0.0%"
    ws["A9"] = "Cobertura de la sección 7 del enunciado"
    ws["A9"].font = Font(name=arial, bold=True)
    cobertura = [("Cinco preguntas respondidas correctamente", "P01–P05, P07, P09–P12, P17, P18, P25–P31, P34"),
                 ("Una pregunta ambigua", "P13"), ("Una pregunta sin periodo explícito", "P01, P14"),
                 ("Una pregunta fuera del alcance", "P15"), ("Una dimensión inexistente", "P16"),
                 ("Comparación entre dos periodos o categorías", "P04, P17, P18"),
                 ("Consulta que no devuelve registros", "P19, P24, P29"), ("Operación no autorizada", "P20, P21"),
                 ("Regresiones de la revisión independiente", "P25–P34")]
    for i, (k, v) in enumerate(cobertura, start=10):
        ws.cell(i, 1, k).font = Font(name=arial)
        ws.cell(i, 2, v).font = Font(name=arial)
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 40

    # ---- Matriz
    ws = wb.create_sheet("Matriz de pruebas")
    cols = [("ID", 7), ("Tipo de caso", 26), ("Pregunta", 40), ("Intención esperada", 34), ("Intención detectada", 44),
            ("Consulta ejecutada", 60), ("Resultado esperado", 44), ("Resultado obtenido", 60), ("Estado", 9),
            ("Observaciones", 50)]
    for j, (titulo, ancho) in enumerate(cols, 1):
        c = ws.cell(1, j, titulo)
        c.font = Font(name=arial, bold=True, color="FFFFFF")
        c.fill = cab_fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = ancho
    for i, f in enumerate(filas, 2):
        valores = [f["id"], f["categoria"], f["pregunta"], f["intencion_esperada"], f["intencion_detectada"],
                   f["consulta"], f["esperado"], f["obtenido"], f["estado"], f["observaciones"]]
        for j, val in enumerate(valores, 1):
            c = ws.cell(i, j, val)
            c.font = Font(name=arial, size=9, bold=(j == 9),
                          color=("006100" if val == "OK" else "9C0006") if j == 9 else "000000")
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = borde
            if j == 9:
                c.fill = PatternFill("solid", fgColor="C6EFCE" if val == "OK" else "FFC7CE")
        ws.row_dimensions[i].height = 150
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:J{len(filas) + 1}"

    # ---- Validaciones
    ws = wb.create_sheet("Reglas aplicadas")
    enc = ["ID", "Regla", "Nombre", "Momento", "Aprobada", "Severidad", "Mensaje"]
    for j, t in enumerate(enc, 1):
        c = ws.cell(1, j, t)
        c.font = Font(name=arial, bold=True, color="FFFFFF")
        c.fill = cab_fill
    r = 2
    for f in filas:
        for val in f["validaciones"]:
            for j, x in enumerate([f["id"], val["regla"], val["nombre"], val["momento"], "Sí" if val["aprobada"] else "No",
                                   val["severidad"], val["mensaje"]], 1):
                ws.cell(r, j, x).font = Font(name=arial, size=9)
            r += 1
    for j, w in enumerate([7, 8, 34, 11, 10, 12, 110], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    wb.save(ruta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="reglas", choices=["reglas", "auto", "llm"])
    ap.add_argument("--equipo", default="XX")
    ap.add_argument("--bdoo", default=None, help="archivo ZODB para la sesión de pruebas (por defecto, el del agente)")
    a = ap.parse_args()

    v = modelo_independiente()
    casos = construir_casos(v)
    tmp = None
    ruta_bdoo = a.bdoo
    try:
        repo = RepositorioBDOO(ruta_bdoo) if ruta_bdoo else RepositorioBDOO()
    except RuntimeError:
        tmp = tempfile.mkdtemp()
        repo = RepositorioBDOO(Path(tmp) / "pruebas.fs")
        print("La BDOO principal está en uso; la sesión de pruebas se guarda en un archivo temporal.")
    repo.inicializar()
    servicios = crear_servicios(a.modo, narrativa_llm=False)
    codigo = repo.ejecutar(lambda root: RepositorioBDOO.nueva_sesion(root, "V-23456789", "Matriz de pruebas").codigo)
    filas = []
    for c in casos:
        o = preguntar(repo, servicios, codigo, c["pregunta"])
        try:
            ok = bool(c["verificar"](o))
        except Exception as e:  # noqa: BLE001
            ok, o["resumen"] = False, o["resumen"] + f" [error de verificación: {e}]"
        obs = []
        if o["advertencias"]:
            obs.append("Advertencias: " + " | ".join(o["advertencias"]))
        fallidas = [f"{x['regla']}" for x in o["validaciones"] if not x["aprobada"]]
        obs.append(f"Reglas activadas: {', '.join(fallidas) if fallidas else 'ninguna (todas aprobadas)'}")
        obs.append(f"Estado de la pregunta en la BDOO: {o['estado']} · IDO {o['ido_pregunta']}")
        consulta = f"{o['consulta']}\n{o['sql']}\nParámetros: {json.dumps(o['parametros'], ensure_ascii=False)}" if o["sql"] \
            else "No se ejecutó SQL (respuesta controlada antes de consultar el Data Mart)"
        filas.append({**c, "intencion_detectada": o["intencion_txt"], "consulta": consulta,
                      "obtenido": f"[{o['tipo']}] {o['resumen']}".replace("**", ""), "estado": "OK" if ok else "FALLA",
                      "observaciones": "\n".join(obs), "validaciones": o["validaciones"]})
        print(f"{c['id']:5} {'OK   ' if ok else 'FALLA'} {o['tipo']:10} {c['pregunta'][:70]}")
    repo.ejecutar(lambda root: root["sesiones"][codigo].cerrar())
    repo.cerrar()
    servicios.datamart.cerrar()
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    salida = RAIZ / "entregables"
    salida.mkdir(exist_ok=True)
    ruta = salida / f"Equipo{a.equipo}_Pruebas.xlsx"
    escribir_excel(filas, ruta, a.equipo, a.modo)
    (RAIZ / "docs" / "evidencias").mkdir(parents=True, exist_ok=True)
    (RAIZ / "docs" / "evidencias" / "pruebas.json").write_text(json.dumps(
        [{k: f[k] for k in ("id", "categoria", "pregunta", "intencion_esperada", "intencion_detectada", "consulta",
                            "esperado", "obtenido", "estado", "observaciones")} for f in filas], ensure_ascii=False, indent=2),
        encoding="utf-8")
    n_ok = sum(f["estado"] == "OK" for f in filas)
    print(f"\n{n_ok}/{len(filas)} casos OK -> {ruta.relative_to(RAIZ)}")
    return 0 if n_ok == len(filas) else 1


if __name__ == "__main__":
    sys.exit(main())
