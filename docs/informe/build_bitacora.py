"""Genera la Bitácora de uso de IA (PDF).   python docs/informe/build_bitacora.py --equipo XX"""
from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from docs.informe.build_informe import CSS, INTEGRANTES  # noqa: E402

CLAUDE = "Claude (Anthropic) · modelo Claude Opus 5.5 · app Claude (asistente de desarrollo con ejecución de código)"

ENTRADAS = [
    {"n": 1, "fecha": "29-10-2026", "componente": "Planificación",
     "prompt": "«Vamos a diseñar y ejecutar un plan para realizar esta asignatura. Dame todas las dudas que tengas al respecto» "
               "(adjuntos: enunciado del Parcial 01 y anuncio de Canvas con fechas).",
     "herramienta": CLAUDE,
     "resultado": "Lista de 14 dudas priorizadas (dataset, motor de la BDOO, motor del Data Mart, LLM, equipo, reparto, interfaz, "
                  "SCD, preguntas adicionales, fecha de la presentación) con una propuesta por defecto para cada una.",
     "validacion": "El equipo contrastó las dudas con el enunciado (secciones 4–11) y con las presentaciones P04 (DW) y P06 (BDOO) del docente.",
     "decision": "Aceptar",
     "justificacion": "Respondimos: el docente no dio dataset (crear uno propio), usar OpenRouter como LLM, mismo equipo de proyecto."},
    {"n": 2, "fecha": "29-10-2026", "componente": "Dataset (fuente operacional)",
     "prompt": "«No dio un dataset, supongo que podemos crear nosotros nuestro propio dataset con la estructura conveniente y "
               "apropiada. Te mando presentaciones del profesor. Para el LLM podemos usar OpenRouter… haz todo el plan tú para ejecutarlo desde acá»",
     "herramienta": CLAUDE,
     "resultado": "Generador determinista data/generar_dataset.py (semilla fija) de una empresa ficticia con errores de calidad sembrados.",
     "validacion": "Se revisaron con pandas las distribuciones por mes, categoría, canal y sucursal. Hallazgos: Tecnología dominaba el "
                   "ingreso porque el canal mayorista compraba entre 6 y 48 laptops por línea, y los precios por rango de categoría "
                   "producían casos absurdos (un mouse más caro que una laptop).",
     "decision": "Modificar",
     "justificacion": "Se corrigieron las cantidades mayoristas por tipo de producto y se fijó un precio de referencia por producto "
                      "(±12 % por marca), para que las conclusiones de negocio fueran verosímiles."},
    {"n": 3, "fecha": "29-10-2026", "componente": "Dataset / SCD2",
     "prompt": "(misma sesión) Ejecución del script SQL sobre el dataset generado.",
     "herramienta": CLAUDE + " + PostgreSQL 16",
     "resultado": "La carga falló: la restricción CHECK ck_cliente_vigencia rechazó una versión de cliente con fecha_fin < fecha_inicio.",
     "validacion": "Se rastreó al generador: algunas reclasificaciones de segmento caían antes de la fecha de alta del cliente.",
     "decision": "Modificar",
     "justificacion": "Se exigió que la reclasificación ocurra al menos 30 días después del alta. La restricción del modelo funcionó "
                      "como control de calidad y se mantiene."},
    {"n": 4, "fecha": "29-10-2026", "componente": "Data Mart (sql/Datamart.sql)",
     "prompt": "(misma sesión) Construir el Data Mart: esquema estrella, grano, claves sustitutas, desconocidos, SCD, ETL, rol de "
               "solo lectura, controles y consultas parametrizadas.",
     "herramienta": CLAUDE,
     "resultado": "Script SQL único e idempotente: esquemas oltp/dm/control, 5 dimensiones + hecho, miembros −1/−2, SCD2, ETL, "
                  "rechazos, rol agente_lector, 3 vistas de control y 10 consultas PREPARE.",
     "validacion": "Ejecución completa en PostgreSQL 16: conciliación 7/7 OK, integridad 10/10 con 0 hallazgos y conciliación "
                   "independiente con pandas sobre los CSV 5/5 OK (ingreso neto idéntico al centavo).",
     "decision": "Aceptar",
     "justificacion": "Los controles demuestran que no hay pérdida ni duplicación de ingresos, cantidades ni tickets."},
    {"n": 5, "fecha": "29-10-2026", "componente": "Decisión SCD",
     "prompt": "(misma sesión) Justificar SCD Tipo 1 vs Tipo 2 para el segmento del cliente y su efecto en el agente.",
     "herramienta": CLAUDE,
     "resultado": "Recomendación de SCD Tipo 2 y una consulta Q4-bis que simula el Tipo 1 usando el segmento actual.",
     "validacion": "Se compararon ambas respuestas sobre el Data Mart: con Tipo 2 el segmento que más cae es Corporativo (−20,6 %); "
                   "con Tipo 1 sería Frecuente (−31,5 %) y Corporativo parecería crecer (+5,5 %).",
     "decision": "Aceptar",
     "justificacion": "La evidencia numérica muestra que el Tipo 1 llevaría al agente a una conclusión falsa."},
    {"n": 6, "fecha": "29-10-2026", "componente": "BDOO (agente/bdoo/)",
     "prompt": "(misma sesión) Implementar las 10 clases mínimas como objetos persistentes, con herencia, encapsulamiento, "
               "polimorfismo, composición y persistencia, siguiendo los conceptos de la clase P06.",
     "herramienta": CLAUDE + " + ZODB",
     "resultado": "Modelo ZODB con 10 clases base, 18 subclases, TDA con validación (equivalente al TDA DATOS/RIF de Oracle), "
                  "Blob como LOB y versionamiento.",
     "validacion": "Pruebas unitarias (clases abstractas, máquina de estados, TDA) y evidencia generada tras cerrar y reabrir la base. "
                   "Hallazgo: los IDO salían vacíos porque ZODB los asigna al confirmar la transacción.",
     "decision": "Modificar",
     "justificacion": "Se agregó un savepoint antes de mostrar los objetos, para que los IDO estén disponibles en la respuesta."},
    {"n": 7, "fecha": "29-10-2026", "componente": "Intérprete por reglas",
     "prompt": "(misma sesión) Intérprete en español que funcione sin internet como respaldo del LLM.",
     "herramienta": CLAUDE,
     "resultado": "Parser por reglas (métricas, periodos, dimensiones, valores, ambigüedad, parámetros faltantes, seguimiento).",
     "validacion": "Se probó con más de 50 preguntas. Errores detectados: (a) «¿cuáles son los canales… del segmento Premium?» devolvía "
                   "límite 1 por la palabra «el segmento»; (b) «¿cómo evolucionó…?» se tomaba como comparación de periodos; (c) «canal "
                   "Instagram» se ignoraba en silencio y devolvía el total; (d) «vendimos» no se reconocía como venta.",
     "decision": "Modificar",
     "justificacion": "Se corrigieron los cuatro casos. El (c) era el más grave porque la respuesta parecía válida: ahora el valor "
                      "llega a la regla RV05, que pide aclaración y lista los valores válidos."},
    {"n": 8, "fecha": "29-10-2026", "componente": "Intérprete LLM (OpenRouter) y regla RV11",
     "prompt": "(misma sesión) Integrar OpenRouter sin que el LLM pueda inventar cifras ni generar SQL.",
     "herramienta": CLAUDE,
     "resultado": "El LLM sólo devuelve un JSON con códigos del catálogo; la narrativa se acepta sólo si todas sus cifras están en el resultado (RV11).",
     "validacion": "El entorno de desarrollo no tenía acceso a openrouter.ai, así que se probó con respuestas simuladas: JSON válido, "
                   "JSON inválido (cae a reglas), valor de filtro inexistente, dimensión inexistente, narrativa con cifras inventadas "
                   "(rechazada) y narrativa respaldada (aceptada).",
     "decision": "Aceptar con reserva",
     "justificacion": "Faltaba la prueba con el LLM real: se hizo en la entrada 15."},
    {"n": 9, "fecha": "29-10-2026", "componente": "Seguridad",
     "prompt": "(misma sesión) Impedir acceso a tablas no autorizadas, instrucciones destructivas y campos inexistentes.",
     "herramienta": CLAUDE,
     "resultado": "Defensa en cuatro capas: RV01 (texto), listas blancas + parámetros, RV07 (SQL) y rol de solo lectura.",
     "validacion": "Pytest con intentos de inyección (DROP, DELETE, comentarios, pg_sleep, oltp.*, control.*, valor malicioso como "
                   "filtro): todos bloqueados o tratados como parámetro.",
     "decision": "Aceptar", "justificacion": "Cumple la sección 6.2 del enunciado aunque se use SQL dinámico."},
    {"n": 10, "fecha": "29-10-2026", "componente": "Pruebas (Pruebas.xlsx)",
     "prompt": "(misma sesión) Matriz de pruebas con los casos obligatorios de la sección 7.",
     "herramienta": CLAUDE,
     "resultado": "25 casos ejecutados automáticamente (scripts/ejecutar_pruebas.py), con el valor esperado calculado por separado con pandas.",
     "validacion": "25/25 OK en la primera versión. La revisión independiente (entrada 14) mostró que P10 compartía un error con el agente: "
                   "ambos agrupaban clientes por nombre.",
     "decision": "Modificar", "justificacion": "Se corrigió P10 y se amplió la matriz a 35 casos (P25–P34 son regresiones de la revisión)."},
    {"n": 11, "fecha": "29-10-2026", "componente": "Diagramas",
     "prompt": "(misma sesión) Diagramas de estrella, de clases y de arquitectura.",
     "herramienta": CLAUDE + " + Mermaid",
     "resultado": "Diagramas Mermaid de estrella y de clases (legibles); el de arquitectura salió ilegible por el cruce de flechas.",
     "validacion": "Revisión visual de cada imagen.",
     "decision": "Rechazar (arquitectura)",
     "justificacion": "Se rehízo a mano el diagrama de arquitectura como SVG. Los otros dos se aceptaron."},
    {"n": 12, "fecha": "29-10-2026", "componente": "Informe técnico y bitácora",
     "prompt": "(misma sesión) Redactar el informe técnico a partir de las evidencias reales.",
     "herramienta": CLAUDE,
     "resultado": "Generador docs/informe/build_informe.py que toma las cifras de los JSON de evidencia (no se transcriben a mano).",
     "validacion": "Revisión visual página por página del PDF. Se corrigió la portada, que se desbordaba a una segunda página.",
     "decision": "Aceptar con revisión del equipo",
     "justificacion": "Cada integrante debe leer la sección de su componente antes de la defensa."},
    {"n": 13, "fecha": "29-10-2026", "componente": "Agente en ejecución (uso de IA dentro del producto)",
     "prompt": "Prompt de sistema en agente/interpretes/llm.py: catálogo de métricas y dimensiones, valores válidos, rango de fechas y 19 "
               "reglas de interpretación; salida JSON obligatoria.",
     "herramienta": "OpenRouter · modelo configurable (por defecto openai/gpt-4o-mini, temperatura 0)",
     "resultado": "Intención estructurada y una interpretación gerencial breve.",
     "validacion": "Automática en cada pregunta: anclaje a la lectura literal, construir_intencion() + RV02–RV06 sobre la intención "
                   "y RV11 sobre la narrativa.",
     "decision": "Aceptar", "justificacion": "Si el LLM falla, el intérprete por reglas garantiza el funcionamiento."},
    {"n": 14, "fecha": "29-10-2026", "componente": "Revisión independiente del agente",
     "prompt": "Encargo a un agente revisor de Claude que no participó en la construcción: «Revisa como el profesor más exigente: verifica "
               "cada requisito del enunciado, prueba el agente con unas 40 preguntas variadas en español (paráfrasis, periodos, "
               "comparaciones, fuera de alcance, operaciones no autorizadas), contrasta cifras con SQL o pandas y lista los defectos».",
     "herramienta": CLAUDE + " (agente revisor independiente)",
     "resultado": "Más de 120 preguntas probadas. Defectos graves: ranking de clientes agrupado por nombre (sumaba empresas distintas), "
                  "división entera en variaciones de unidades y tickets, periodos mal leídos («T1 2026», «último semestre», «enero "
                  "a marzo»), año parcial comparado contra año completo, preguntas fuera de alcance respondidas con cifras («tickets "
                  "anulados», «proyección»), miembros «Sin correspondencia» encabezando rankings y la regla RV01 bloqueando "
                  "preguntas de negocio («¿qué productos debemos eliminar del catálogo?»).",
     "validacion": "Cada defecto se reprodujo y se verificó contra SQL o pandas. Se agregó una prueba de regresión para cada uno (P25–P34 "
                   "y 6 pruebas unitarias). En la segunda pasada (unas 75 preguntas nuevas, 7 cifras verificadas con pandas) aparecieron "
                   "otros defectos: clientes nombrados en la pregunta, seguimientos («¿y por canal?», «¿y en los tres meses anteriores?», "
                   "«¿y el segundo?»), «frente al de 2025» y verbos como «facturamos». También se corrigieron.",
     "decision": "Modificar",
     "justificacion": "Los defectos producían respuestas incorrectas con apariencia confiable, que es el peor caso para un agente "
                      "gerencial. La matriz pasó de 25 a 35 casos, todos correctos."},
    {"n": 15, "fecha": "29-10-2026", "componente": "Intérprete LLM: validación con OpenRouter real y anclaje",
     "prompt": "Prompt de sistema del agente (agente/interpretes/llm.py) más las preguntas en lote, enviado a openai/gpt-4o-mini en "
               "el chat de OpenRouter con la cuenta del equipo: la matriz completa (dos versiones del prompt) y dos conjuntos de "
               "preguntas nuevas (14 y 12) que no están en la matriz.",
     "herramienta": "OpenRouter · openai/gpt-4o-mini (respuestas reales) + " + CLAUDE + " para el análisis y el código",
     "resultado": "El LLM solo acertó 22/33 y 17/34 casos de la matriz. Inventó periodos («ingreso neto por mes» → últimos 12 meses), "
                  "inventó los canales de «compare dos canales», tomó «ventas» como venta bruta o unidades, puso valores en la "
                  "dimensión equivocada, devolvió la operación en el campo tipo y marcó preguntas inocentes como operación no "
                  "autorizada. Reforzar el prompt (reglas 11–19) no lo resolvió: en la segunda corrida aparecieron errores nuevos.",
     "validacion": "Las respuestas reales se grabaron en docs/evidencias/llm_openrouter/ y se reprodujeron con scripts/validar_llm.py "
                   "contra la misma verificación de la matriz (oráculo pandas) y, para las preguntas nuevas, contra la interpretación "
                   "esperada escrita de antemano. En el segundo conjunto nuevo, antes de los ajustes: reglas 11/12, LLM solo 7/12, "
                   "híbrido 8/12. Después: híbrido 33/33, 34/34, 14/14 y 12/12; matriz por reglas 35/35; pytest 41/41.",
     "decision": "Modificar",
     "justificacion": "Se agregó el anclaje (anclar()): el LLM aporta la comprensión semántica y la lectura literal fija los hechos "
                      "escritos en la pregunta (fechas, valores, sentido del orden). Lo inventado se descarta y queda como supuesto "
                      "visible. Salvedades: las reglas del anclaje se escribieron después de ver las fallas, así que esos 100 % no "
                      "son una medida ciega, y las preguntas se enviaron en lote, no una por una como hace el agente. También se "
                      "corrigió un defecto del agente que apareció aquí: un «total» con dimensión mostraba sólo la primera fila."},
    {"n": 16, "fecha": "30-10-2026", "componente": "Matriz de pruebas en vivo con la API key del equipo",
     "prompt": "python scripts/ejecutar_pruebas.py --modo auto --equipo 02 en la computadora del equipo, con la key parcial1 de "
               "OpenRouter: el agente llama a openai/gpt-4o-mini una vez por pregunta, con el contexto de la sesión.",
     "herramienta": "OpenRouter · openai/gpt-4o-mini + " + CLAUDE + " para el diagnóstico",
     "resultado": "32/35. P04 y P29: el LLM pidió un periodo que no hacía falta (en P29 el periodo, 2025, estaba en la pregunta) y "
                  "el agente pidió aclaración. P23b («¿y en 2026?»): la cifra fue correcta, pero se perdió la marca de pregunta "
                  "de seguimiento.",
     "validacion": "Se revisó la intención detectada y las reglas activadas de cada falla (docs/evidencias/pruebas.json). Detalle en "
                   "docs/evidencias/llm_openrouter/matriz_en_vivo_2026-10-30.md. Tras el ajuste: dos pruebas unitarias nuevas "
                   "(43/43) y una simulación de la matriz con esas tres respuestas reales da 35/35.",
     "decision": "Modificar",
     "justificacion": "Si el LLM pide parámetros que la lectura literal sí encuentra, se usa la lectura literal y queda el supuesto "
                      "visible. En los seguimientos se conserva la marca. Falta repetir la corrida en vivo con el código corregido."},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equipo", default="XX")
    a = ap.parse_args()
    e = html.escape
    filas = []
    for x in ENTRADAS:
        filas.append(f"""<div class="ent"><div class="cab">Entrada {x['n']} · {e(x['componente'])}
        <span>{e(x['fecha'])}</span></div><table>
        <tr><td class="k">Prompt utilizado</td><td>{e(x['prompt'])}</td></tr>
        <tr><td class="k">Herramienta empleada</td><td>{e(x['herramienta'])}</td></tr>
        <tr><td class="k">Resultado obtenido</td><td>{e(x['resultado'])}</td></tr>
        <tr><td class="k">Componente afectado</td><td>{e(x['componente'])}</td></tr>
        <tr><td class="k">Validación técnica</td><td>{e(x['validacion'])}</td></tr>
        <tr><td class="k">Decisión</td><td><b>{e(x['decision'])}</b></td></tr>
        <tr><td class="k">Justificación</td><td>{e(x['justificacion'])}</td></tr></table></div>""")
    resumen = "".join(f"<tr><td>{x['n']}</td><td>{e(x['componente'])}</td><td>{e(x['decision']) or '—'}</td></tr>" for x in ENTRADAS)
    doc = f"""<html><head><meta charset="utf-8"><style>{CSS}
    .ent {{ border: 1px solid #cbd5e1; border-radius: 6px; margin: 10px 0 14px; page-break-inside: avoid; }}
    .ent .cab {{ background: #1F3864; color: #fff; padding: 6px 10px; font-weight: bold; border-radius: 6px 6px 0 0; }}
    .ent .cab span {{ float: right; font-weight: normal; }}
    .ent table {{ margin: 0; }} .ent td.k {{ width: 24%; font-weight: bold; background: #f1f5f9 !important; }}
    </style></head><body>
    <h1 style="margin-top:0">Bitácora de uso de IA · Parcial 01</h1>
    <p><b>Equipo {e(a.equipo)}</b> · {', '.join(INTEGRANTES)} · Tópicos Especiales para la Gestión de Datos · Prof. Armen Djenanian</p>
    <div class="caja">La IA se usó como <b>asistente de desarrollo</b> (Claude) y como <b>componente del producto</b> (LLM vía OpenRouter
    dentro del agente). Ningún resultado de la IA se aceptó sin una validación técnica verificable: ejecución en PostgreSQL,
    conciliación independiente con pandas, pruebas unitarias, matriz de pruebas y revisión visual. Las entradas registran también
    los resultados que se modificaron o rechazaron. Pendiente del equipo: ejecutar el agente con la API key en su .env
    (python scripts/ejecutar_pruebas.py --modo auto), que llama al LLM pregunta por pregunta, y registrar el resultado.</div>
    <h2>Resumen de decisiones</h2><table><thead><tr><th style="width:8%">#</th><th>Componente</th><th style="width:26%">Decisión</th></tr></thead>
    <tbody>{resumen}</tbody></table>
    <h2>Entradas</h2>{''.join(filas)}</body></html>"""
    ruta_html = RAIZ / "docs" / "informe" / "bitacora.html"
    ruta_html.write_text(doc, encoding="utf-8")
    ruta_pdf = RAIZ / "entregables" / f"Equipo{a.equipo}_BitacoraIA.pdf"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(ruta_html.as_uri())
        pg.pdf(path=str(ruta_pdf), format="Letter", print_background=True, display_header_footer=True,
               header_template="<span></span>",
               footer_template="<div style='font-size:8px;width:100%;text-align:center;color:#64748b;font-family:Arial'>"
                               f"Equipo {a.equipo} · Bitácora de IA — pág. <span class='pageNumber'></span> de <span class='totalPages'></span></div>",
               margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"})
        b.close()
    print(f"-> {ruta_pdf.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
