"""
Interfaz web del agente (Streamlit).   Ejecutar:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agente.bdoo.repositorio import RepositorioBDOO  # noqa: E402
from agente.catalogo import DIMENSIONES, METRICAS  # noqa: E402
from agente.cli import crear_servicios  # noqa: E402
from agente.config import CONFIG  # noqa: E402
from agente.redactor import etiqueta_columna, presentar, tabla_formateada  # noqa: E402

st.set_page_config(page_title="Agente Analítico de Ventas", page_icon="📊", layout="wide")

EJEMPLOS = [
    "¿Cuál fue el ingreso neto por mes?",
    "¿Cuáles son las cinco categorías con mayor margen bruto?",
    "¿Qué sucursal presenta el ticket promedio más alto?",
    "¿Qué segmento de clientes redujo más su volumen de compra?",
    "¿Qué canal concentra el mayor valor de ventas?",
    "Compare el margen de Tienda física y Mayorista B2B durante los últimos tres meses disponibles",
    "¿Qué producto lidera las ventas de Bebidas en el segundo trimestre de 2026?",
    "¿Qué 10 clientes concentran el mayor ingreso y qué porcentaje representan?",
    "¿Qué porcentaje de descuento otorga cada canal?",
    "¿Qué productos tienen el margen porcentual más bajo?",
    "¿Cuál fue el mejor canal?",
    "¿Cuál es el inventario disponible por sucursal?",
]


@st.cache_resource
def repositorio() -> RepositorioBDOO:
    repo = RepositorioBDOO()
    repo.inicializar()
    return repo


@st.cache_resource
def servicios(modo: str):
    return crear_servicios(modo)


def nueva_sesion(doc: str) -> str:
    return repositorio().ejecutar(lambda root: RepositorioBDOO.nueva_sesion(root, doc, "Streamlit").codigo)


def preguntar(codigo: str, texto: str, modo: str) -> dict:
    serv = servicios(modo)

    def hacer(root):
        sesion = root["sesiones"][codigo]
        p = root["agente"].responder(sesion, texto, serv)
        RepositorioBDOO.asignar_oids(root)
        r = p.respuesta
        res = r.resultado
        cab, filas_fmt = tabla_formateada(res, _codigo_metrica(r.metrica)) if res is not None and not res.esta_vacio() else ([], [])
        return {
            "texto": texto, "tipo": r.tipo, "resumen": r.resumen, "interpretacion": r.interpretacion,
            "origen_interp": r.origen_interpretacion, "markdown": presentar(r, sesion.usuario, incluir_tabla=False),
            "opciones": r.opciones, "advertencias": r.advertencias, "validaciones": r.validaciones,
            "sql": r.sql, "parametros": r.parametros, "metrica": r.metrica, "regla": r.regla_calculo,
            "periodo": r.periodo, "filtros": r.filtros, "dimension": r.dimension, "consulta": r.consulta_codigo,
            "fuentes": [(f.tabla, f.tipo, f.ido) for f in r.fuentes],
            "columnas": res.columnas if res else [], "filas": res.filas if res else [], "cab": cab, "filas_fmt": filas_fmt,
            "intencion": p.intencion.a_dict() if p.intencion else None, "pregunta": p.a_dict(),
            "respuesta_ido": r.ido, "resultado_ido": res.ido if res else None,
            "operacion": p.intencion.operacion if p.intencion else None,
            "metrica_cod": p.intencion.metrica if p.intencion else None,
            "dimension_cod": p.intencion.dimension if p.intencion else None,
            "muestra_sql": sesion.usuario.muestra_sql(),
        }
    return repositorio().ejecutar(hacer)


def _codigo_metrica(nombre: str):
    return next((c for c, m in METRICAS.items() if m.nombre == nombre), None)


# ------------------------------------------------------------------------------------------ sidebar
repo = repositorio()
usuarios = repo.ejecutar(lambda root: [(k, u.nombre, u.rol) for k, u in root["usuarios"].items()])
with st.sidebar:
    st.title("📊 Agente Analítico")
    st.caption("Distribuidora Ávila C.A. · Data Mart de Ventas + BDOO")
    etiquetas = {k: f"{n} ({r})" for k, n, r in usuarios}
    doc = st.selectbox("Usuario", list(etiquetas), format_func=etiquetas.get,
                       help="El gerente ve una respuesta ejecutiva; el analista ve además el SQL (polimorfismo).")
    opciones_modo = ["auto", "reglas"] + (["llm"] if CONFIG.llm_disponible else [])
    modo = st.radio("Intérprete", opciones_modo, horizontal=True,
                    help="auto: LLM (OpenRouter) con respaldo por reglas · reglas: determinista sin internet")
    st.caption(f"LLM: {'✅ ' + CONFIG.openrouter_model if CONFIG.llm_disponible else '⚠️ sin OPENROUTER_API_KEY (se usan reglas)'}")
    if "sesion" not in st.session_state or st.session_state.get("doc") != doc or st.button("🆕 Nueva sesión"):
        st.session_state.sesion = nueva_sesion(doc)
        st.session_state.doc = doc
        st.session_state.historial = []
    st.caption(f"Sesión: `{st.session_state.sesion}`")
    st.divider()
    st.subheader("Preguntas de ejemplo")
    for q in EJEMPLOS:
        if st.button(q, use_container_width=True, key=f"ej-{q}"):
            st.session_state.pendiente = q

tab_chat, tab_bdoo, tab_cat = st.tabs(["💬 Agente", "🗄️ BDOO · trazabilidad", "📚 Catálogo"])


# ------------------------------------------------------------------------------------------ chat
def mostrar(item: dict, idx: int):
    with st.chat_message("user"):
        st.write(item["texto"])
    with st.chat_message("assistant"):
        icono = {"RESPUESTA": "✅", "SIN_DATOS": "📭", "ACLARACION": "❓", "RECHAZO": "⛔", "ERROR": "⚠️"}[item["tipo"]]
        st.markdown(f"{icono} {item['resumen']}")
        if item["tipo"] == "RESPUESTA":
            if item["interpretacion"]:
                st.markdown(f"**Interpretación gerencial** ({item['origen_interp']}): {item['interpretacion']}")
            if item["filas"] and len(item["filas"]) > 1:
                st.dataframe(pd.DataFrame(item["filas_fmt"], columns=item["cab"]), hide_index=True, use_container_width=True)
                _grafico(item)
            st.caption(f"Fuente: {', '.join(t for t, _, _ in item['fuentes'])} · {item['consulta']} · "
                       f"métrica: {item['regla']}")
            if item["muestra_sql"] and item["sql"]:      # perfil analista (polimorfismo de Usuario)
                st.code(item["sql"], language="sql")
        for a in item["advertencias"]:
            st.warning(a, icon="⚠️")
        if item["opciones"] and item["tipo"] == "ACLARACION":
            _aclaracion(item, idx)
        with st.expander("🔎 Evidencia y trazabilidad"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Métrica:** {item['metrica'] or '—'}  \n**Regla de cálculo:** {item['regla'] or '—'}  \n"
                            f"**Periodo:** {item['periodo'] or '—'}  \n**Filtros:** {item['filtros'] or 'ninguno'}  \n"
                            f"**Dimensión:** {item['dimension'] or '—'}  \n**Consulta del catálogo:** {item['consulta'] or '—'}")
                if item["fuentes"]:
                    st.markdown("**Fuentes:** " + ", ".join(f"`{t}` ({tp}, IDO {i})" for t, tp, i in item["fuentes"]))
            with c2:
                st.markdown(f"**IDO pregunta:** `{item['pregunta']['ido']}` · estado **{item['pregunta']['estado']}**  \n"
                            f"**IDO intención:** `{item['pregunta']['intencion_ido']}`  \n"
                            f"**IDO respuesta:** `{item['respuesta_ido']}`  \n**IDO resultado:** `{item['resultado_ido']}`")
            if item["sql"] and item["muestra_sql"]:
                st.code(item["sql"], language="sql")
                st.caption(f"Parámetros: {json.dumps(item['parametros'], ensure_ascii=False)}")
            elif item["sql"]:
                st.caption("El SQL ejecutado y sus parámetros quedan registrados en la BDOO; se muestran al perfil analista.")
            st.markdown("**Reglas de validación aplicadas**")
            st.dataframe(pd.DataFrame(item["validaciones"])[["regla", "nombre", "momento", "aprobada", "severidad", "mensaje"]]
                         if item["validaciones"] else pd.DataFrame(), hide_index=True, use_container_width=True)
            st.markdown("**Intención detectada**")
            st.json(item["intencion"] or {}, expanded=False)


def _aclaracion(item: dict, idx: int):
    """Botones/selectores para completar una pregunta ambigua o con parámetros faltantes."""
    import re
    opciones = item["opciones"]
    if all(o in METRICAS for o in opciones):
        cols = st.columns(min(len(opciones), 4))
        for j, o in enumerate(opciones[:8]):
            if cols[j % len(cols)].button(METRICAS[o].nombre, key=f"op-{idx}-{j}"):
                st.session_state.pendiente = f"{item['texto'].rstrip('?¿. ')} según {METRICAS[o].nombre.lower()}"
                st.rerun()
        return
    texto = item["texto"].rstrip(" .?")
    faltantes = (item["intencion"] or {}).get("faltantes") or []
    m = re.search(r"\b(dos|2|tres|3)\s+(canales|categor[ií]as|sucursales|segmentos|regiones|productos)\b", texto, re.I)
    if m:
        n = 3 if m.group(1).lower() in ("tres", "3") else 2
        elegidos = st.multiselect(f"Elija {n} {m.group(2)}", opciones, max_selections=n, key=f"ms-{idx}")
        if st.button("Comparar", key=f"cmp-{idx}", disabled=len(elegidos) < 2):
            st.session_state.pendiente = texto.replace(m.group(0), " y ".join(elegidos))
            st.rerun()
        return
    c1, c2, c3 = st.columns([2, 2, 1])
    valor = c1.selectbox("Valor", opciones, key=f"sb-{idx}")
    periodo = c2.text_input("Periodo", "el último trimestre", key=f"ti-{idx}") if "periodo" in faltantes else ""
    if c3.button("Consultar", key=f"cs-{idx}"):
        nuevo = re.sub(r"\b(una|cierta|alguna|determinad[ao])\s+(categor[ií]a|sucursal|canal|segmento|regi[oó]n)(\s+determinad[ao]s?)?",
                       lambda mm: f"{'el' if mm.group(2).lower() in ('canal', 'segmento') else 'la'} {mm.group(2)} {valor}", texto, flags=re.I)
        if nuevo == texto:          # p. ej. cliente con nombre repetido: se agrega el elegido (incluye su código)
            nuevo = f"{texto} — {valor}"
        if periodo:
            nuevo = re.sub(r"\s*y\s+(un\s+)?periodos?\s+determinad[oa]s?|\s*(en\s+)?(un\s+)?periodo\s+determinad[oa]", "", nuevo, flags=re.I)
            nuevo = f"{nuevo} en {periodo}"
        st.session_state.pendiente = nuevo
        st.rerun()


def _grafico(item: dict):
    dim, met, op = item["dimension_cod"], item["metrica_cod"], item["operacion"]
    if not dim or not met or met not in item["columnas"] or dim not in item["columnas"]:
        return
    df = pd.DataFrame(item["filas"], columns=item["columnas"])
    if op == "comparacion_miembros" and len(item["columnas"]) > 2 and item["columnas"][1] in DIMENSIONES:
        des = item["columnas"][1]
        df = df[df[des] != "Total periodo"].pivot(index=des, columns=dim, values=met)
        st.bar_chart(df)
    elif op == "tendencia":
        st.line_chart(df.set_index(dim)[[met]].rename(columns={met: etiqueta_columna(met)}))
    elif op == "ranking":
        st.bar_chart(df.set_index(dim)[[met]].rename(columns={met: etiqueta_columna(met)}), horizontal=True)
    elif op == "comparacion_periodos" and "valor_base" in df:
        st.bar_chart(df.set_index(dim)[["valor_base", "valor_actual"]])


with tab_chat:
    st.header("Pregunte en lenguaje natural")
    st.caption("Las cifras salen exclusivamente del Data Mart (PostgreSQL, esquema dm). Cada interacción queda "
               "registrada como objetos en la BDOO (ZODB).")
    for i, item in enumerate(st.session_state.historial):
        mostrar(item, i)
    texto = st.chat_input("Ej.: ¿Qué canal concentra el mayor valor de ventas en 2026?")
    texto = texto or st.session_state.pop("pendiente", None)
    if texto:
        with st.spinner("Interpretando, consultando y validando…"):
            item = preguntar(st.session_state.sesion, texto, modo)
        st.session_state.historial.append(item)
        st.rerun()


# ------------------------------------------------------------------------------------------ BDOO
with tab_bdoo:
    st.header("Objetos persistentes del agente (ZODB)")
    st.caption("Cada objeto tiene un IDO (identificador de objeto) asignado por la BDOO. Las referencias entre "
               "objetos son apuntadores suaves resueltos por ZODB.")

    def listar(root):
        return [(k, s.usuario.nombre, len(s.preguntas), s.inicio.strftime("%d-%m %H:%M"), s.ido)
                for k, s in reversed(list(root["sesiones"].items()))]
    sesiones = repo.ejecutar(listar)
    st.dataframe(pd.DataFrame(sesiones, columns=["Sesión", "Usuario", "Preguntas", "Inicio", "IDO"]).head(30),
                 hide_index=True, use_container_width=True)
    elegida = st.selectbox("Ver sesión", [s[0] for s in sesiones] if sesiones else [])
    if elegida:
        def detalle(root):
            s = root["sesiones"][elegida]
            preguntas = []
            for p in s.preguntas:
                r = p.respuesta
                preguntas.append({
                    "pregunta": p.a_dict(), "intencion": p.intencion.a_dict() if p.intencion else None,
                    "respuesta": r.a_dict() if r else None,
                    "resultado": r.resultado.a_dict() if r and r.resultado else None,
                    "consulta": r.resultado.consulta.a_dict() if r and r.resultado else None,
                })
            return s.a_dict(), s.usuario.a_dict(), preguntas
        ses, usu, preguntas = repo.ejecutar(detalle)
        c1, c2 = st.columns(2)
        c1.markdown("**Sesion**")
        c1.json(ses, expanded=False)
        c2.markdown("**Usuario**")
        c2.json(usu, expanded=False)
        for p in preguntas:
            with st.expander(f"[{p['pregunta']['estado']}] {p['pregunta']['texto']}  ·  IDO {p['pregunta']['ido']}"):
                cols = st.columns(5)
                for col, clave in zip(cols, ["pregunta", "intencion", "respuesta", "resultado", "consulta"]):
                    col.markdown(f"**{clave.capitalize()}**")
                    col.json(p[clave] or {}, expanded=False)

    st.subheader("Historial de versiones de un objeto (versionamiento de ZODB)")
    oid_txt = st.text_input("IDO (hex) de un objeto, p. ej. el de una ConsultaAnalitica o del AgenteAnalitico")
    if oid_txt:
        try:
            hist = repo.db.history(bytes.fromhex(oid_txt), size=20)
            st.dataframe(pd.DataFrame([{"tid": h["tid"].hex(), "fecha": str(h["time"]), "descripción": h["description"],
                                        "tamaño": h["size"]} for h in hist]), hide_index=True)
        except Exception as e:  # noqa: BLE001
            st.error(f"No se encontró el objeto: {e}")


# ------------------------------------------------------------------------------------------ catálogo
with tab_cat:
    def catalogo(root):
        a = root["agente"]
        return (a.a_dict(), [c.a_dict() for c in a.catalogo], [r.a_dict() for r in a.reglas],
                [f.a_dict() for f in a.fuentes.values()])
    ag, consultas, reglas, fuentes = repo.ejecutar(catalogo)
    st.markdown(f"**{ag['nombre']}** · IDO `{ag['ido']}` · estadísticas: {ag['estadisticas']}")
    st.subheader("Consultas analíticas (ConsultaAnalitica)")
    st.dataframe(pd.DataFrame(consultas)[["codigo", "clase", "ido", "nombre", "version", "ejecuciones", "descripcion"]],
                 hide_index=True, use_container_width=True)
    st.subheader("Reglas de validación (ReglaValidacion)")
    st.dataframe(pd.DataFrame(reglas)[["codigo", "clase", "ido", "momento", "severidad", "evaluaciones", "fallos", "descripcion"]],
                 hide_index=True, use_container_width=True)
    st.subheader("Fuentes de datos (FuenteDato)")
    st.dataframe(pd.DataFrame(fuentes)[["tabla", "tipo", "ido", "usos", "campos"]], hide_index=True, use_container_width=True)
    st.subheader("Métricas")
    st.dataframe(pd.DataFrame([{"código": m.codigo, "nombre": m.nombre, "aditividad": m.aditividad, "regla": m.regla}
                               for m in METRICAS.values()]), hide_index=True, use_container_width=True)
    st.subheader("Dimensiones")
    st.dataframe(pd.DataFrame([{"código": d.codigo, "nombre": d.nombre, "tabla": d.tabla, "columna": d.columna,
                                "jerarquía": d.jerarquia} for d in DIMENSIONES.values()]), hide_index=True,
                 use_container_width=True)
