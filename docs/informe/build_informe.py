"""
Genera el Informe Técnico (PDF) a partir de las evidencias reales del proyecto.
  python docs/informe/build_informe.py --equipo XX
Requiere: playwright + chromium (o abrir el HTML generado e imprimirlo a PDF desde el navegador).
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from agente.catalogo import DIMENSIONES, METRICAS  # noqa: E402

INTEGRANTES = ["Mathias Carstens", "Mikel Muñoz", "Leonardo Reyes", "Federico Celis", "Fernando Álvarez"]
EV = RAIZ / "docs" / "evidencias"
DIAG = RAIZ / "docs" / "diagramas"

CSS = """
@page { size: Letter; }
* { box-sizing: border-box; }
body { font-family: 'Arial', 'Helvetica', sans-serif; font-size: 10.5pt; color: #1f2937; line-height: 1.45; }
h1 { font-size: 17pt; color: #1F3864; border-bottom: 2px solid #1F3864; padding-bottom: 4px; margin-top: 26px; page-break-after: avoid; }
h2 { font-size: 13pt; color: #1F3864; margin-top: 18px; page-break-after: avoid; }
h3 { font-size: 11pt; color: #334155; margin-top: 12px; page-break-after: avoid; }
p { margin: 6px 0; text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #1F3864; color: #fff; text-align: left; padding: 5px 6px; }
td { border: 1px solid #cbd5e1; padding: 4px 6px; vertical-align: top; }
tr:nth-child(even) td { background: #f8fafc; }
code, pre { font-family: 'Courier New', monospace; font-size: 8.4pt; }
pre { background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 8px; white-space: pre-wrap; page-break-inside: avoid; }
.caja { border-left: 4px solid #1F3864; background: #eef2ff; padding: 8px 12px; margin: 10px 0; page-break-inside: avoid; }
.ok { color: #166534; font-weight: bold; } .falla { color: #991b1b; font-weight: bold; }
figure { margin: 10px 0; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; border: 1px solid #e2e8f0; }
figcaption { font-size: 9pt; color: #475569; margin-top: 4px; }
.portada { height: 21.5cm; display: flex; flex-direction: column; justify-content: space-between; page-break-after: always; }
.portada .top { font-size: 11pt; color: #475569; }
.portada h1 { border: none; font-size: 26pt; margin: 0; line-height: 1.15; }
.portada .sub { font-size: 14pt; color: #334155; margin-top: 10px; }
.portada table td { border: none; padding: 3px 8px 3px 0; font-size: 11pt; background: none !important; }
.toc li { margin: 2px 0; }
.small { font-size: 8.8pt; color: #475569; }
"""


def img(nombre: str, caption: str, ancho: str = "100%") -> str:
    b64 = base64.b64encode((DIAG / nombre).read_bytes()).decode()
    return f'<figure><img src="data:image/png;base64,{b64}" style="max-width:{ancho}"/><figcaption>{caption}</figcaption></figure>'


def tabla(cabecera, filas, anchos=None) -> str:
    estilo = [(' style="width:%s"' % anchos[i]) if anchos else "" for i in range(len(cabecera))]
    th = "".join(f"<th{estilo[i]}>{h}</th>" for i, h in enumerate(cabecera))
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def e(x) -> str:
    return html.escape(str(x))


def construir(equipo: str) -> str:
    conc = json.loads((EV / "conciliacion.json").read_text(encoding="utf-8"))
    pruebas = json.loads((EV / "pruebas.json").read_text(encoding="utf-8"))
    n_ok = sum(p["estado"] == "OK" for p in pruebas)
    ev_bdoo = json.loads((EV / "evidencia_bdoo.json").read_text(encoding="utf-8"))

    h = [f"<html><head><meta charset='utf-8'><title>Equipo{equipo}_Informe_Parcial01</title><style>{CSS}</style></head><body>"]
    # ------------------------------------------------------------------ portada
    h.append(f"""<div class="portada"><div class="top">Universidad Católica Andrés Bello · Escuela de Ingeniería Informática<br/>
    Tópicos Especiales para la Gestión de Datos · Prof. Armen Djenanian</div>
    <div><h1>Agente Analítico de IA con Data Mart y Base de Datos Orientada a Objetos</h1>
    <div class="sub">Parcial 01 · Informe técnico</div>
    <div class="sub" style="font-size:12pt">Caso: Distribuidora Ávila C.A. (empresa ficticia) · Data Mart de Ventas</div></div>
    <div><table><tr><td><b>Equipo</b></td><td>{e(equipo)}</td></tr>
    <tr><td><b>Integrantes</b></td><td>{'<br/>'.join(INTEGRANTES)}</td></tr>
    <tr><td><b>Fecha de entrega</b></td><td>30 de octubre de 2026</td></tr>
    <tr><td><b>Defensa</b></td><td>2 de noviembre de 2026</td></tr>
    <tr><td><b>Versión</b></td><td>1.0 (final)</td></tr></table></div></div>""")

    h.append("""<h1>Contenido</h1><ol class="toc"><li>Descripción del problema y alcance</li><li>Arquitectura de la solución</li>
    <li>Diseño dimensional: grano, hechos, dimensiones y jerarquías</li><li>Diagrama del esquema estrella</li>
    <li>Reglas de cálculo y controles de calidad</li><li>Diseño de clases, relaciones y patrones orientados a objetos</li>
    <li>Flujo de interpretación, consulta, validación y respuesta</li><li>Resultados de pruebas</li>
    <li>Limitaciones y mejoras futuras</li><li>Anexos: reproducibilidad y entregables</li></ol>
    <div class="caja"><b>Resumen ejecutivo.</b> Se construyó un agente que responde preguntas gerenciales en lenguaje natural
    consultando exclusivamente un Data Mart de ventas en PostgreSQL (esquema estrella, SCD Tipo 2 en el segmento del cliente),
    mediante un catálogo de consultas parametrizadas y once reglas de validación, y que registra cada interacción como
    objetos persistentes en una BDOO (ZODB). El Data Mart concilia al centavo con la fuente (7/7 controles SQL y 5/5 controles
    independientes con pandas), los 10 controles de integridad dan 0 hallazgos y la matriz de pruebas obtuvo """
             f"""<b>{n_ok}/{len(pruebas)} casos correctos</b> contra valores esperados calculados de forma independiente.</div>""")

    # ------------------------------------------------------------------ 1
    h.append("""<h1>1. Descripción del problema y alcance</h1>
    <p>Distribuidora Ávila C.A. es una empresa comercial (ficticia, creada para este parcial) con 7 sucursales en Venezuela,
    5 canales de venta (tienda física, e-commerce web, app móvil, delivery por WhatsApp y mayorista B2B), 10 categorías de
    productos y cuatro segmentos de clientes (Minorista, Frecuente, Premium y Corporativo). Hoy sus consultas de
    indicadores dependen de personal técnico. La gerencia necesita formular preguntas en lenguaje natural y recibir
    respuestas <b>verificables, trazables y limitadas estrictamente a los datos disponibles</b>.</p>
    <p>Como el docente no entregó un conjunto de datos, el equipo generó una <b>fuente operacional sintética y
    determinista</b> (<code>data/generar_dataset.py</code>, semilla fija) que simula las exportaciones del POS y del CRM entre el
    01-01-2025 y el 30-09-2026: 30.970 tickets, 99.890 líneas, 2.360 clientes con 2.736 versiones de segmento, 75 productos.
    Para demostrar los controles, la fuente incluye <b>errores de calidad sembrados a propósito</b>:</p>""")
    h.append(tabla(["Problema sembrado en la fuente", "Volumen", "Tratamiento en el Data Mart"], [
        ["Ticket sin cliente (consumidor final)", "792 tickets", "cliente_sk = −1 «No informado» (no se pierde la venta)"],
        ["cliente_id inexistente en el maestro", "129 tickets", "cliente_sk = −2 «Sin correspondencia»"],
        ["producto_id inexistente en el catálogo", "202 líneas", "producto_sk = −2 «Sin correspondencia»"],
        ["Tickets anulados", "495 tickets", "Excluidos del hecho; registrados en control.etl_rechazo"],
        ["Líneas duplicadas (re-sincronización del POS)", "384 líneas", "Deduplicadas por (ticket, línea); registradas"],
        ["Cantidad ≤ 0", "108 líneas", "Rechazadas y registradas"],
        ["Producto sin subcategoría / cliente sin ciudad", "4 / 25", "«Sin subcategoría» / «No informada»"],
    ]))
    h.append("""<h2>1.1 Alcance funcional</h2><p>El agente responde preguntas sobre <b>ventas, rentabilidad, clientes, productos,
    canales, sucursales y tendencias temporales</b>, con 11 métricas y 19 dimensiones de análisis. Soporta totales, rankings,
    series temporales, comparaciones entre periodos y comparaciones entre miembros de una dimensión. Fuera de alcance
    (y reconocido como tal): inventario, personal, proveedores, devoluciones, impuestos, presupuesto, etc.</p>
    <h2>1.2 Preguntas adicionales propuestas por el equipo</h2>""")
    h.append(tabla(["Pregunta", "Valor gerencial"], [
        ["A1. ¿Qué 10 clientes concentran el mayor ingreso y qué porcentaje representan?",
         "Mide la <b>dependencia de pocos clientes</b> (riesgo comercial): si un cliente grande se va, ¿cuánto ingreso se pierde? "
         "En los datos, los 10 primeros suman ≈4,2 % del ingreso: dependencia baja. Los clientes se agrupan por su clave "
         "(<code>cliente_id</code>), no por nombre, porque hay razones sociales repetidas entre empresas distintas."],
        ["A2. ¿Qué porcentaje de descuento otorga cada canal?",
         "Revela la <b>política comercial efectiva</b>: el canal Mayorista B2B concede ≈12 % frente a ≈1,5 % de los demás, "
         "lo que explica su menor margen. Permite renegociar escalas de descuento."],
        ["A3. ¿Qué productos tienen el margen porcentual más bajo?",
         "Detecta productos que <b>venden mucho pero dejan poco</b> (Tecnología, Electrodomésticos). Insumo para revisar precios, "
         "costos de proveedor o retirar referencias."],
    ], ["45%", "55%"]))

    # ------------------------------------------------------------------ 2
    h.append("""<h1>2. Arquitectura de la solución</h1>
    <p>La solución sigue la arquitectura de Inteligencia de Negocios vista en clase (fuentes → integración → base analítica →
    capa lógica → visualización), a la que se agrega el agente y su BDOO. La separación de responsabilidades es estricta:</p>""")
    h.append(tabla(["Componente", "Tecnología", "Responsabilidad"], [
        ["Fuente operacional", "CSV → esquema <code>oltp</code>", "Datos tal como llegan del POS/CRM (normalizados, con errores)."],
        ["Data Mart (verdad analítica)", "PostgreSQL · esquema <code>dm</code>", "Estrella de ventas, histórica, limpia; única fuente que consulta el agente."],
        ["Control", "PostgreSQL · esquema <code>control</code>", "Lotes ETL, rechazos y vistas de conciliación e integridad."],
        ["Agente", "Python 3 · <code>agente/</code>", "Interpreta, selecciona consulta, valida y redacta la respuesta."],
        ["Intérprete LLM", "OpenRouter (API OpenAI) · respaldo por reglas", "Traduce la pregunta a un JSON con códigos del catálogo (nunca SQL)."],
        ["BDOO (comportamiento y trazabilidad)", "ZODB (FileStorage + Blobs)", "Objetos del agente, sesiones, preguntas, respuestas, reglas y evidencias."],
        ["Interfaz", "Streamlit · CLI", "Chat con evidencia, explorador de objetos y catálogo."],
    ], ["24%", "28%", "48%"]))
    h.append(img("arquitectura.png", "Figura 1. Arquitectura y flujo del agente (los números siguen el flujo mínimo 2.1 del enunciado)."))

    # ------------------------------------------------------------------ 3
    h.append("""<h1>3. Diseño dimensional</h1>
    <p>Se aplicó la metodología <b>Kimball (bottom-up)</b>: un Data Mart departamental de Ventas con dimensiones conformadas
    (fecha, producto, cliente, sucursal, canal) reutilizables por futuros Data Marts (inventario, compras).</p>
    <h2>3.1 Proceso de negocio y grano</h2>
    <div class="caja"><b>Grano de dm.fact_ventas:</b> «Una fila por cada línea de producto de un ticket de venta completado, es
    decir, un producto vendido en un ticket, en una fecha, sucursal y canal, a un cliente».</div>
    <p>Se eligió el grano <b>atómico</b> (línea de ticket) porque es el más flexible: permite responder por producto y
    categoría, y agregar hacia arriba sin perder información. La clave primaria <code>(numero_ticket, linea_ticket)</code>
    garantiza que no existan dos filas para el mismo grano, lo que <b>evita duplicar ingresos, cantidades y conteos</b>.
    <code>numero_ticket</code> es una <b>dimensión degenerada</b>: no tiene tabla propia, pero permite contar transacciones
    sin duplicar (<code>COUNT(DISTINCT numero_ticket)</code>) y rastrear cada fila hasta la fuente.</p>
    <h2>3.2 Hechos y métricas</h2>""")
    h.append(tabla(["Métrica", "Tipo", "Regla de cálculo / tratamiento"], [
        ["cantidad, monto_bruto, descuento, ingreso_neto, costo_total, margen_bruto", "<b>Aditivas</b>",
         "Se suman por cualquier dimensión (incluido el tiempo). Se almacenan en el hecho con CHECK que garantizan su coherencia."],
        ["(ninguna en este hecho)", "<b>Semiaditivas</b>",
         "Un hecho transaccional no almacena saldos. Ejemplos de semiaditivas serían las existencias de inventario o el saldo por "
         "cobrar: sumables por producto o sucursal, pero no a lo largo del tiempo (en el tiempo se toma el último valor o el promedio). "
         "Si se agregara un hecho de inventario (snapshot periódico) aparecerían ahí."],
        ["precio_unitario, margen %, ticket promedio, % descuento, clientes activos, n.º de transacciones", "<b>No aditivas</b>",
         "Nunca se suman ni se promedian: se <b>recalculan</b> a partir de sumas (p. ej. margen % = SUM(margen)/SUM(ingreso)). "
         "Por eso la comparación entre canales usa GROUPING SETS para recalcular el total del periodo."],
    ], ["32%", "13%", "55%"]))
    h.append("<h2>3.3 Dimensiones y jerarquías</h2>")
    h.append(tabla(["Dimensión", "Clave sustituta", "Jerarquía / atributos", "Cambios históricos"], [
        ["dim_fecha", "fecha_sk = AAAAMMDD", "día → mes → trimestre → semestre → año; nombre del día, fin de semana", "No aplica (calendario 2024–2026)"],
        ["dim_producto", "producto_sk (identity)", "producto → subcategoría → categoría; marca", "SCD Tipo 1 (se corrige)"],
        ["dim_cliente", "cliente_sk (identity)", "cliente → segmento; tipo de cliente; ciudad", "<b>SCD Tipo 2</b> en segmento; Tipo 1 en nombre/ciudad"],
        ["dim_sucursal", "sucursal_sk (identity)", "sucursal → ciudad → estado → región", "SCD Tipo 1"],
        ["dim_canal", "canal_sk (identity)", "canal → tipo de canal", "SCD Tipo 1"],
    ], ["15%", "20%", "40%", "25%"]))
    h.append("""<h2>3.4 Claves sustitutas</h2><p>Todas las dimensiones usan claves sustitutas enteras sin significado de negocio,
    generadas por el Data Mart. Su finalidad: (a) <b>aislar</b> el DW de cambios o reutilización de códigos en la fuente;
    (b) permitir <b>varias versiones</b> de un mismo cliente (SCD2: el mismo <code>cliente_id</code> tiene varias
    <code>cliente_sk</code>); (c) representar <b>miembros especiales</b> (−1, −2) sin inventar códigos de negocio; y (d) joins más
    compactos y rápidos. La única excepción deliberada es <code>fecha_sk</code> (AAAAMMDD), convención estándar de Kimball.</p>
    <h2>3.5 Desconocidos, faltantes y claves sin correspondencia</h2>
    <p>Cada dimensión tiene dos miembros especiales: <b>−1 «No informado»</b> (la fuente trae la clave vacía) y <b>−2 «Sin
    correspondencia»</b> (la fuente trae una clave que no existe en el maestro). Así ninguna venta se descarta (el ingreso
    concilia al centavo) y la excepción queda <b>visible</b>: la regla RV09 del agente advierte cuando un resultado incluye estos
    miembros. Los atributos faltantes se reemplazan con valores explícitos («Sin subcategoría», «No informada») en lugar de NULL.
    Los registros que no son ventas válidas (anulados, duplicados, cantidad ≤ 0) se excluyen y quedan en
    <code>control.etl_rechazo</code>. Los rankings ordenan los miembros especiales <b>al final</b>, para que nunca
    «ganen» un ranking (p. ej. la categoría con peor margen), pero siguen visibles.</p>
    <p><b>Identidad vs. nombre.</b> En la fuente hay 638 razones sociales compartidas por clientes distintos. Por eso el agente
    agrupa por la clave natural (se muestra «nombre (C02263)»): agrupar por nombre sumaría empresas diferentes.</p>
    <h2>3.6 Pregunta obligatoria de diseño: ¿Tipo 1 o Tipo 2 para el segmento del cliente?</h2>
    <div class="caja"><b>Decisión: SCD Tipo 2.</b> Si un cliente cambia de segmento se <b>conserva la historia</b>: se cierra la
    versión anterior (<code>fecha_fin</code>, <code>es_actual = false</code>) y se crea una nueva con otra <code>cliente_sk</code>.
    El ETL asigna a cada venta la versión <b>vigente en la fecha de la compra</b>.</div>
    <p><b>Efecto sobre las consultas del agente.</b> En la fuente, 376 clientes cambiaron de segmento (entre ellos 71 de los 210
    corporativos, el 34 %, reclasificados a Frecuente en 2026). La tabla compara la respuesta a «¿qué segmento redujo más su volumen de
    compra?» (ingreso neto ene–sep 2026 vs ene–sep 2025) con ambas decisiones:</p>""")
    h.append(tabla(["Segmento", "SCD Tipo 2 (elegido)", "SCD Tipo 1 (se sobrescribe)"], [
        ["Corporativo", "757.336 → 601.480 (<b>−20,6 %</b>)", "504.417 → 532.105 (+5,5 %)"],
        ["Frecuente", "227.917 → 260.571 (+14,3 %)", "480.937 → 329.642 (<b>−31,5 %</b>)"],
        ["Minorista", "304.448 → 352.294 (+15,7 %)", "283.097 → 348.418 (+23,1 %)"],
        ["Premium", "114.767 → 142.379 (+24,1 %)", "136.017 → 146.559 (+7,8 %)"],
        ["<b>Respuesta del agente</b>", "<b>Corporativo</b> (correcta)", "Frecuente (<b>incorrecta</b>)"],
    ]))
    h.append("""<p>Con Tipo 1 las compras de 2025 de los clientes que dejaron de ser corporativos se atribuirían a «Frecuente»,
    inflando artificialmente su base y escondiendo la caída real del segmento Corporativo. El agente daría la conclusión
    opuesta. Con Tipo 2 cada venta conserva el segmento que el cliente tenía al comprar. La consulta «segmento actual» sigue
    siendo posible filtrando <code>es_actual = true</code>. Los atributos que no tienen valor analítico histórico (nombre, ciudad)
    se manejan como Tipo 1.</p>
    <h2>3.7 Datos operacionales vs. analíticos</h2>""")
    h.append(tabla(["Característica", "oltp.* (operacional)", "dm.* (analítico)"], [
        ["Propósito", "Registrar transacciones", "Consultar y analizar"],
        ["Estructura", "Normalizada (ticket / detalle / maestros)", "Desnormalizada en estrella"],
        ["Calidad", "Duplicados, huérfanos, anulados", "Limpia, deduplicada, con miembros especiales"],
        ["Historia", "El CRM sobrescribe el segmento actual", "Conserva versiones (SCD2), no volátil"],
        ["Claves", "Códigos de negocio (C00001, P0001)", "Claves sustitutas enteras"],
        ["Acceso del agente", "<b>Prohibido</b> (REVOKE + regla RV07)", "Sólo SELECT con el rol agente_lector"],
    ]))
    h.append("""<p><b>Alcance deliberado.</b> La fuente trae la forma de pago del ticket, pero no se incluyó en el Data Mart porque
    ninguna pregunta del enunciado la requiere. Por eso el agente responde que la dimensión «método de pago» no existe, en vez
    de inventarla. Agregarla sería una dimensión pequeña (junk dimension) sin cambiar el grano.</p>""")

    # ------------------------------------------------------------------ 4
    h.append("<h1>4. Diagrama del esquema estrella</h1>")
    h.append(img("estrella.png", "Figura 2. Esquema estrella del Data Mart de Ventas (dm). PK: clave primaria; FK: clave foránea."))
    h.append("""<p>Restricciones implementadas: claves primarias en todas las tablas, claves foráneas del hecho hacia las cinco
    dimensiones, <code>CHECK</code> de reglas de cálculo (bruto = cantidad × precio; neto = bruto − descuento; margen = neto − costo;
    cantidad &gt; 0; descuento ≤ bruto), unicidad de claves naturales y de versión SCD2 <code>(cliente_id, fecha_inicio)</code>,
    vigencia válida (<code>fecha_inicio ≤ fecha_fin</code>) e índices sobre cada clave foránea del hecho.</p>""")

    # ------------------------------------------------------------------ 5
    h.append("<h1>5. Reglas de cálculo y controles de calidad</h1><h2>5.1 Reglas de cálculo</h2>")
    h.append(tabla(["Indicador", "Regla", "Aditividad"],
                   [[m.nombre, e(m.regla), m.aditividad] for m in METRICAS.values()], ["22%", "60%", "18%"]))
    h.append("<h2>5.2 Conciliación del Data Mart contra la fuente</h2><p>Vista <code>control.v_conciliacion_estado</code>, que compara la fuente válida (oltp deduplicada, completada, cantidad &gt; 0) contra dm.fact_ventas:</p>")
    h.append(tabla(["Control", "Fuente", "Data Mart", "Diferencia", "Estado"],
                   [[e(c["control"]), c["valor_fuente"], c["valor_dm"], c["diferencia"],
                     f"<span class='ok'>{c['estado']}</span>"] for c in conc["conciliacion_sql"]]))
    h.append("<p>Además, <code>scripts/setup_datamart.py</code> hace una <b>conciliación independiente</b>: recalcula los totales con pandas leyendo directamente los CSV (sin PostgreSQL):</p>")
    h.append(tabla(["Control", "CSV (pandas)", "Data Mart", "Estado"],
                   [[c["control"], c["csv"], c["dm"], f"<span class='ok'>{c['estado']}</span>"] for c in conc["conciliacion_independiente"]]))
    h.append("<h2>5.3 Integridad referencial y del modelo</h2>")
    h.append(tabla(["Control (control.v_integridad)", "Hallazgos"],
                   [[e(c["control"]), f"<span class='ok'>{c['hallazgos']}</span>"] for c in conc["integridad"]], ["80%", "20%"]))
    h.append("<h2>5.4 Excepciones documentadas</h2>")
    h.append(tabla(["Dimensión / motivo", "Miembro", "Líneas", "Tickets", "Ingreso neto", "% ingreso"],
                   [[e(x["dimension"]), e(x["miembro"]), x["lineas"], x["tickets"].replace("None", "—"),
                     x["ingreso_neto"].replace("None", "—"), x["pct_ingreso"].replace("None", "—")] for x in conc["excepciones"]]))

    # ------------------------------------------------------------------ 6
    h.append("""<h1>6. Diseño de clases, relaciones y patrones orientados a objetos</h1>
    <p>La BDOO <b>no replica las tablas dimensionales</b>: almacena los objetos del agente, su comportamiento y la trazabilidad de cada
    interacción. Las diez clases mínimas del enunciado existen con esos nombres y responsabilidades, más subclases que
    especializan el comportamiento.</p>""")
    h.append(img("clases.png", "Figura 3. Diagrama de clases de la BDOO (herencia ◁, composición ◆, agregación ◇, asociación →)."))
    h.append(tabla(["Clase", "Responsabilidad en la solución"], [
        ["AgenteAnalitico", "Coordina interpretación, consulta, validación y respuesta (<code>responder()</code>); agrega el catálogo, las reglas y las fuentes."],
        ["Usuario → Gerente, Analista", "Quien pregunta. Abstracta; <code>nivel_detalle()</code> y <code>muestra_sql()</code> son polimórficos (el analista ve el SQL)."],
        ["Sesion", "Agrupa las preguntas y guarda la <b>memoria operativa</b> (última intención) para preguntas de seguimiento («¿y en 2025?»)."],
        ["Pregunta", "Texto, fecha, filtros e intención; <b>máquina de estados</b> RECIBIDA → INTERPRETADA → RESPONDIDA / SIN_DATOS / ACLARACION / RECHAZADA."],
        ["Intencion", "Necesidad analítica: tipo, métrica, dimensión, periodo (TDA), filtros (TDA), operación, orden, límite, supuestos."],
        ["ConsultaAnalitica → 5 subclases", "Plantilla SQL, parámetros, fuentes y versión. <code>aplica_a()</code> y <code>construir_sql()</code> polimórficos."],
        ["ResultadoConsulta", "Datos devueltos y metadatos (SQL, parámetros, duración, error) + exportación CSV en un <b>Blob (LOB)</b>."],
        ["RespuestaAgente", "Explicación final, métrica y regla, periodo, filtros, fuentes, advertencias y validaciones aplicadas."],
        ["FuenteDato", "Data Mart, tabla y campos usados. Objetos <b>compartidos</b>: muchas respuestas apuntan al mismo objeto."],
        ["ReglaValidacion → 11 subclases", "Controles previos a responder; <code>validar()</code> polimórfico; estadísticas de evaluaciones y fallos."],
    ], ["28%", "72%"]))
    h.append("<h2>6.1 Conceptos de BDOO (clase P06) y su implementación</h2>")
    h.append(tabla(["Concepto", "Implementación en el proyecto"], [
        ["Identificador de objeto (IDO)", "<code>_p_oid</code> asignado por ZODB (expuesto como <code>ido</code>): técnico, sin significado de negocio, inmutable. Ej.: AgenteAnalitico IDO <code>0000000000000002</code>."],
        ["Objetos complejos", "Sesion contiene Preguntas; cada Pregunta contiene Intencion y RespuestaAgente; ésta contiene ResultadoConsulta."],
        ["Métodos", "Comportamiento dentro de cada objeto: <code>responder</code>, <code>construir_sql</code>, <code>validar</code>, <code>cambiar_estado</code>, <code>recordar</code>…"],
        ["Encapsulamiento", "Estado en atributos privados (<code>_texto</code>, <code>_estado</code>); sólo propiedades de lectura y métodos que validan (p. ej. transiciones de estado inválidas lanzan error)."],
        ["Herencia", "ObjetoAgente → 10 clases; Usuario → Gerente/Analista; ConsultaAnalitica → 5; ReglaValidacion → 11."],
        ["Polimorfismo", "Mismo mensaje, distinta implementación: <code>aplica_a/construir_sql</code> (consultas), <code>validar</code> (reglas), <code>nivel_detalle</code> (usuarios). Equivale al ejemplo Puerta/Ventana de «Cerrar»."],
        ["Apuntadores suaves", "Las referencias entre objetos persistentes se guardan como OID y ZODB las resuelve al acceder (carga perezosa)."],
        ["LOB y TDA", "Blob con el CSV del resultado. TDA inmutables con validación: <code>DocumentoIdentidad.formato()</code> (equivalente al TDA DATOS/RIF de Oracle visto en clase), <code>Periodo</code>, <code>Filtro</code>."],
        ["Versionamiento", "Explícito: <code>ConsultaAnalitica.nueva_version()</code> con historial; implícito: FileStorage guarda cada revisión de un objeto (<code>db.history(oid)</code>)."],
        ["Recuperación y concurrencia", "Transacciones ACID de ZODB (<code>commit/abort</code>), control optimista de concurrencia (ConflictError → reintento)."],
        ["Clustering", "Índices OOBTree (B-Trees) para sesiones y usuarios; los objetos de cada pregunta (Pregunta, Intencion, RespuestaAgente, ResultadoConsulta) se escriben juntos en la misma transacción."],
        ["Protocolos de comunicación", "Los objetos se serializan con el protocolo de ZODB (pickle con referencias por OID) y se intercambian con la interfaz como diccionarios JSON (<code>a_dict()</code>). Con ZEO, el mismo protocolo serviría objetos por red a varios procesos."],
    ], ["24%", "76%"]))
    h.append("""<h2>6.2 Patrones de diseño</h2>""")
    h.append(tabla(["Patrón", "Dónde"], [
        ["Strategy", "Intérpretes intercambiables: InterpreteLLM, InterpreteReglas, InterpreteHibrido."],
        ["Template Method", "<code>ConsultaAnalitica.ejecutar()</code> (construir → ejecutar → empaquetar) y <code>ReglaValidacion.aplicar()</code>."],
        ["Chain of Responsibility", "Cadena de 11 reglas por momento (texto, intención, SQL, resultado, narrativa)."],
        ["Factory", "<code>crear_catalogo()</code>, <code>crear_reglas()</code>, <code>crear_interprete()</code>."],
        ["Facade / Repository", "<code>DataMart</code> (acceso de solo lectura) y <code>RepositorioBDOO</code> (raíz, transacciones, reintentos)."],
        ["State", "Pregunta con transiciones de estado controladas."],
        ["Inyección de dependencias", "Los servicios técnicos (conexión, LLM) se inyectan en <code>responder()</code> y no se persisten."],
    ], ["26%", "74%"]))
    h.append("""<h2>6.3 Mecanismo de persistencia y justificación</h2>
    <p>Se eligió <b>ZODB</b>, una base de datos orientada a objetos nativa de Python: persiste los objetos tal cual (sin mapeo
    objeto-relacional), asigna IDO, mantiene referencias entre objetos, soporta herencia y polimorfismo de forma transparente,
    almacena LOB (Blobs), ofrece transacciones ACID con historial de revisiones y B-Trees para índices. Alternativas evaluadas:
    usar PostgreSQL objeto-relacional (tipos compuestos) habría mezclado la BDOO con el motor del Data Mart, lo que la rúbrica
    señala como confusión de responsabilidades; un ORM sobre tablas no es una BDOO. Limitación conocida: FileStorage admite un solo
    proceso escritor (se resolvería con ZEO en producción).</p>""")
    p0 = ev_bdoo["preguntas"][0]
    h.append(f"""<h2>6.4 Ejemplo de objetos almacenados (sesión completa)</h2>
    <p>Extraído de <code>docs/evidencias/evidencia_bdoo.md</code>, generado tras <b>cerrar y reabrir</b> la base:</p>
    <pre>Sesion {e(ev_bdoo['sesion']['codigo'])}  IDO {ev_bdoo['sesion']['ido']}  usuario IDO {ev_bdoo['sesion']['usuario_ido']}
 └─ Pregunta IDO {p0['pregunta']['ido']}  «{e(p0['pregunta']['texto'])}»  estados {' → '.join(x[0] for x in p0['pregunta']['historial_estados'])}
     ├─ Intencion IDO {p0['intencion']['ido']}  {e(p0['intencion']['intencion'])} · {p0['intencion']['operacion']} · {p0['intencion']['metrica']} · {p0['intencion']['dimension']} · límite {p0['intencion']['limite']}
     └─ RespuestaAgente IDO {p0['respuesta']['ido']}  {p0['respuesta']['tipo']}
         ├─ ResultadoConsulta IDO {p0['resultado']['ido']}  {p0['resultado']['n_filas']} fila(s), {p0['resultado']['duracion_ms']} ms, LOB {p0['resultado']['lob_csv_bytes']} bytes
         │   └─ ConsultaAnalitica IDO {p0['consulta']['ido']}  {p0['consulta']['codigo']} {e(p0['consulta']['nombre'])}
         └─ FuenteDato IDO {', '.join(p0['respuesta']['fuentes_ido'])}  ({', '.join(p0['respuesta']['fuentes'])})
Resumen: {e(p0['respuesta']['resumen'].replace('**', ''))}</pre>""")

    # ------------------------------------------------------------------ 7
    h.append("""<h1>7. Flujo de interpretación, consulta, validación y respuesta</h1>
    <h2>7.1 Interpretación</h2><p>El intérprete produce un JSON con: tipo, operación, métrica, dimensión, periodo, periodo de
    comparación, filtros, orden, límite y desglose. En modo <b>auto</b> se usa el LLM de OpenRouter con un prompt que contiene sólo el
    catálogo (códigos de métricas y dimensiones, valores válidos y rango de fechas) y reglas de interpretación; su salida se
    trata como <b>dato no confiable</b> y se valida. Si el LLM falla o no hay API key, se usa el intérprete por reglas (determinista,
    sin internet), lo que garantiza la demostración en vivo. Ejemplo del enunciado:</p>
    <pre>«¿Cuál fue la categoría con mayor margen durante el segundo trimestre?»
→ intención: analizar_rentabilidad | métrica: margen_bruto | dimensión: categoria | periodo: T2-2026
  (supuesto explícito: «no se indicó el año, se asumió el más reciente con datos») | operación: ranking desc | límite: 1</pre>
    <h2>7.2 Acceso controlado al Data Mart</h2><p>Se implementó un <b>catálogo de consultas parametrizadas</b> (5 plantillas). Los
    identificadores SQL salen de listas blancas (<code>agente/catalogo.py</code>) y los valores viajan como parámetros
    (<code>%(p_desde)s</code>, <code>ANY(%(f0)s)</code>). Defensa en profundidad de cuatro capas: (1) RV01 bloquea en el texto pedidos de
    escritura, DDL, credenciales o inyección; (2) el LLM no puede producir SQL; (3) RV07 inspecciona el SQL final (sólo SELECT/WITH, una
    sentencia, sin palabras prohibidas, sólo tablas dm.*); (4) el rol <code>agente_lector</code> sólo tiene SELECT sobre dm, con
    transacciones READ ONLY y <code>statement_timeout</code> de 5 s.</p>
    <h2>7.3 Reglas de validación</h2>""")
    reglas = [("RV01", "texto", "bloqueante", "Operación autorizada (sólo lectura)"), ("RV02", "intención", "bloqueante", "Alcance del Data Mart (fuera de alcance → no inventa)"),
              ("RV03", "intención", "bloqueante", "Dimensión existente"), ("RV04", "intención", "bloqueante", "Criterio explícito (ambigüedad / parámetros faltantes)"),
              ("RV05", "intención", "bloqueante", "Valores de filtro existentes (con sugerencias)"), ("RV06", "intención", "advertencia", "Periodo disponible / asumido"),
              ("RV07", "SQL", "bloqueante", "SQL seguro de sólo lectura"), ("RV08", "resultado", "bloqueante", "Resultado con registros (vacío ≠ cero)"),
              ("RV09", "resultado", "advertencia", "Miembros desconocidos en el resultado"), ("RV10", "resultado", "advertencia", "Consistencia de totales contra consulta de control"),
              ("RV11", "narrativa", "advertencia", "Narrativa del LLM respaldada por cifras del resultado")]
    h.append(tabla(["Regla", "Momento", "Severidad", "Control"], [list(r) for r in reglas], ["10%", "14%", "14%", "62%"]))
    h.append("""<h2>7.4 Respuesta con evidencia</h2><p>Toda respuesta incluye: resultado cuantitativo o categórico; métrica y regla de
    cálculo; periodo y filtros; dimensión; interpretación gerencial breve; fuente (tabla de hechos, dimensiones y código de la
    consulta con su SQL y parámetros) y advertencias. Las cifras salen siempre de plantillas deterministas sobre el resultado; el
    LLM sólo puede aportar la interpretación y es descartada si menciona una cifra que no está en el resultado (RV11).</p>
    <h2>7.5 Límites y ambigüedad</h2>""")
    h.append(tabla(["Situación", "Comportamiento"], [
        ["«¿Cuál fue el mejor canal?»", "ACLARACION: explicita los criterios posibles (ingreso, margen, unidades, ticket promedio) y ofrece botones."],
        ["«Compare el margen de dos canales…» sin decir cuáles", "ACLARACION con la lista de canales; no elige por el usuario."],
        ["Pregunta sin periodo", "Usa todo el rango disponible y lo advierte de forma explícita (RV06)."],
        ["Fuera de alcance (inventario, clima…)", "RECHAZO que explica qué sí puede responder; no inventa."],
        ["Dimensión inexistente (vendedor, método de pago)", "RECHAZO con la lista de dimensiones disponibles."],
        ["Consulta sin registros (Jardinería en 2025)", "SIN_DATOS: informa el vacío y aclara que no lo reporta como cero."],
        ["Operación no autorizada / inyección", "RECHAZO antes de interpretar (RV01)."],
        ["Seguimiento («¿y en 2025?», «ahora compáralo con el mismo trimestre de 2025»)", "Reutiliza la última intención de la Sesion (memoria operativa) y lo advierte."],
        ["Año en curso incompleto («2026 vs 2025»)", "Alinea ambos periodos a los meses disponibles (ene–sep vs ene–sep) y lo explicita."],
        ["Miembro sin ventas en una comparación (Lechería en 2025)", "Lo informa como advertencia; no lo muestra como cero."],
        ["Valor inexistente («canal Instagram»)", "ACLARACION con los valores válidos (RV05)."],
        ["Proyecciones, anulados, devoluciones", "RECHAZO: el Data Mart sólo tiene ventas históricas completadas."],
    ], ["38%", "62%"]))

    # ------------------------------------------------------------------ 8
    h.append(f"""<h1>8. Resultados de pruebas</h1><p>La matriz completa está en <code>Equipo{e(equipo)}_Pruebas.xlsx</code>. El resultado
    esperado de cada caso numérico se calcula <b>independientemente</b> con pandas sobre los CSV de la fuente (sin PostgreSQL ni
    código del agente); el caso es OK sólo si el agente devuelve exactamente ese valor. Resultado: <b class="ok">{n_ok}/{len(pruebas)} OK</b>.
    Además, 35 pruebas unitarias (pytest) cubren TDA, máquina de estados, polimorfismo, seguridad SQL e intérprete.</p>
    <div class="caja"><b>Revisión independiente.</b> Antes de la entrega, un revisor que no participó en la construcción probó el
    agente con más de 120 preguntas parafraseadas. Encontró defectos que la primera matriz (25 casos) no cubría: el ranking de
    clientes agrupaba por nombre (y el valor esperado de P10 repetía el mismo supuesto), había división entera en las variaciones
    de conteos, se interpretaban mal periodos como «T1 2026» sin «de» o «el último semestre», se comparaba un año parcial contra un
    año completo y algunas preguntas fuera de alcance recibían cifras. Una segunda pasada con unas 75 preguntas nuevas
    encontró otros casos (clientes nombrados por su razón social, que puede repetirse, y preguntas de seguimiento). Todos se
    corrigieron y se agregaron los casos de regresión P25–P34. Si un nombre de cliente es ambiguo, el agente pide el código en vez
    de sumar clientes distintos. La lección: un «valor esperado independiente» debe evitar también los supuestos del código.</div>""")
    h.append(tabla(["ID", "Tipo de caso", "Pregunta", "Obtenido (resumen)", "Estado"],
                   [[p["id"], e(p["categoria"]), e(p["pregunta"]), e(p["obtenido"][:260]), f"<span class='ok'>{p['estado']}</span>"
                     if p["estado"] == "OK" else f"<span class='falla'>{p['estado']}</span>"] for p in pruebas],
                   ["6%", "18%", "26%", "43%", "7%"]))

    # ------------------------------------------------------------------ 9
    h.append("""<h1>9. Limitaciones y mejoras futuras</h1><h2>Limitaciones</h2><ul>
    <li>Los datos son sintéticos: las conclusiones de negocio ilustran el funcionamiento, no la realidad de una empresa.</li>
    <li>El intérprete por reglas cubre las construcciones frecuentes en español; frases muy coloquiales requieren el LLM.</li>
    <li>Una consulta agrupa por una sola dimensión (más un desglose temporal en comparaciones); no hay tablas cruzadas de dos dimensiones.</li>
    <li>ZODB FileStorage admite un solo proceso escritor: la app y el CLI no pueden abrir la misma base a la vez.</li>
    <li>El hecho es transaccional: no hay métricas semiaditivas (inventario) ni hecho de devoluciones.</li>
    <li>La calidad de la interpretación por LLM depende del modelo elegido en OpenRouter; por eso su salida siempre se valida.</li></ul>
    <h2>Mejoras futuras</h2><ul>
    <li>Agregar un hecho de inventario (snapshot periódico) con métricas semiaditivas y dimensiones conformadas.</li>
    <li>Consultas de dos dimensiones (pivot) y drill-down guiado por jerarquías (año → trimestre → mes).</li>
    <li>ZEO (servidor ZODB) para varios procesos concurrentes y autenticación real de usuarios.</li>
    <li>Carga incremental del ETL con detección de cambios (CDC) y SCD2 automatizado desde la bitácora del CRM.</li>
    <li>Evaluación automática del LLM con la matriz de pruebas en cada cambio de modelo (regresión semántica).</li>
    <li>Gráficos y exportación de respuestas a PDF desde la interfaz.</li></ul>""")

    # ------------------------------------------------------------------ anexos
    h.append(f"""<h1>10. Anexos: reproducibilidad y entregables</h1><pre>pip install -r requirements.txt
cp .env.example .env                       # credenciales locales (no incluidas en el zip)
python scripts/setup_datamart.py --crear-db   # crea, carga, ETL, rol de solo lectura y concilia
python scripts/inicializar_bdoo.py
streamlit run app/streamlit_app.py         # o: python -m agente.cli -p "pregunta"
pytest -q &amp;&amp; python scripts/ejecutar_pruebas.py --equipo {e(equipo)}</pre>""")
    h.append(tabla(["Archivo", "Contenido"], [
        [f"Equipo{e(equipo)}_Informe_Parcial01.pdf", "Este informe."],
        [f"Equipo{e(equipo)}_Datamart.sql", "Creación de tablas, claves, restricciones y relaciones; carga; ETL; rol; controles; consultas analíticas."],
        [f"Equipo{e(equipo)}_AgenteIA.zip", "Código fuente organizado, dependencias, .env.example, README con instrucciones, datos de la fuente, diagramas y evidencias."],
        [f"Equipo{e(equipo)}_Pruebas.xlsx", "Matriz de casos de prueba (pregunta, intención esperada y detectada, consulta, esperado, obtenido, estado, observaciones)."],
        [f"Equipo{e(equipo)}_BitacoraIA.pdf", "Bitácora de uso de IA."],
        [f"Equipo{e(equipo)}_Defensa.pptx", "Presentación de la defensa."],
    ], ["35%", "65%"]))
    h.append(f"<p class='small'>Documento generado el {date.today():%d-%m-%Y} con <code>docs/informe/build_informe.py</code> a partir de las evidencias del repositorio.</p>")
    h.append("</body></html>")
    return "\n".join(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equipo", default="XX")
    a = ap.parse_args()
    salida = RAIZ / "entregables"
    salida.mkdir(exist_ok=True)
    ruta_html = RAIZ / "docs" / "informe" / "informe.html"
    ruta_html.write_text(construir(a.equipo), encoding="utf-8")
    ruta_pdf = salida / f"Equipo{a.equipo}_Informe_Parcial01.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(ruta_html.as_uri())
        pg.pdf(path=str(ruta_pdf), format="Letter", print_background=True, display_header_footer=True,
               header_template="<span></span>",
               footer_template="<div style='font-size:8px;width:100%;text-align:center;color:#64748b;font-family:Arial'>"
                               f"Equipo {a.equipo} · Parcial 01 · Agente Analítico de IA — pág. <span class='pageNumber'></span> de "
                               "<span class='totalPages'></span></div>",
               margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"})
        b.close()
    print(f"-> {ruta_pdf.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
