"""
Redacción de la respuesta gerencial con evidencia.

Las CIFRAS de la respuesta salen siempre del ResultadoConsulta mediante plantillas deterministas.
El LLM (si está disponible) sólo puede proponer la "interpretación gerencial", que se descarta si
menciona cifras que no están en el resultado (regla RV11).
"""
from __future__ import annotations

from agente.catalogo import DIMENSIONES, METRICAS

ETIQUETA_COL = {"participacion_pct": "Participación %", "variacion_pct": "Variación %", "valor_base": "Periodo base",
                "valor_actual": "Periodo actual", "variacion": "Variación", "lineas": "Líneas", "total": "Total"}


# ------------------------------------------------------------------------------------ formato
def _miles(x: float, dec: int) -> str:
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if x < 0 else "") + s


def fmt(valor, formato: str) -> str:
    if valor is None:
        return "—"
    if not isinstance(valor, (int, float)):
        return str(valor)
    if formato == "usd":
        return f"USD {_miles(valor, 2)}"
    if formato == "pct":
        return f"{_miles(valor, 2)} %"
    if formato == "pp":
        return f"{'+' if valor > 0 else ''}{_miles(valor, 2)} pp"
    if formato == "entero":
        return _miles(valor, 0)
    return _miles(valor, 2)


def formato_columna(col: str, metrica: str | None) -> str:
    if col in METRICAS:
        return METRICAS[col].formato
    if col in ("participacion_pct", "variacion_pct"):
        return "pct"
    if col in ("valor_base", "valor_actual", "variacion") and metrica:
        f = METRICAS[metrica].formato
        return "pp" if (col == "variacion" and f == "pct") else f
    if col == "lineas":
        return "entero"
    return "texto"


def etiqueta_columna(col: str) -> str:
    if col in METRICAS:
        return METRICAS[col].nombre
    if col in DIMENSIONES:
        return DIMENSIONES[col].nombre
    return ETIQUETA_COL.get(col, col)


def tabla_formateada(resultado, metrica: str | None, max_filas: int = 50) -> tuple[list[str], list[list[str]]]:
    cols = resultado.columnas
    cab = [etiqueta_columna(c) for c in cols]
    filas = [[fmt(v, formato_columna(c, metrica)) for c, v in zip(cols, f)] for f in resultado.filas[:max_filas]]
    return cab, filas


def tabla_markdown(resultado, metrica: str | None, max_filas: int = 30) -> str:
    cab, filas = tabla_formateada(resultado, metrica, max_filas)
    lineas = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    lineas += ["| " + " | ".join(f) + " |" for f in filas]
    if resultado.n_filas > max_filas:
        lineas.append(f"| … {resultado.n_filas - max_filas} filas más | " + " | " * (len(cab) - 1))
    return "\n".join(lineas)


# ------------------------------------------------------------------------------------ resumen
def _filtros_txt(intencion) -> str:
    return "; ".join(f.describir() for f in intencion.filtros)


def resumen_y_interpretacion(intencion, resultado) -> tuple[str, str]:
    m = METRICAS[intencion.metrica]
    f = m.formato
    filas = resultado.como_dicts()
    per = str(intencion.periodo)
    filtros = _filtros_txt(intencion)
    con_filtros = f" ({filtros})" if filtros else ""
    op = intencion.operacion

    if op == "total" or not intencion.dimension and op != "comparacion_periodos":
        fila = filas[0]
        extra = ""
        if "transacciones" in fila and intencion.metrica != "transacciones":
            extra = f", sobre {fmt(fila['transacciones'], 'entero')} tickets"
        if "margen_pct" in fila and intencion.metrica != "margen_pct":
            extra = f", equivalente a un margen de {fmt(fila['margen_pct'], 'pct')}"
        resumen = f"{m.nombre}{con_filtros} en {per}: **{fmt(fila[intencion.metrica], f)}**{extra}."
        return resumen, "Valor agregado del periodo; puede desglosarse por mes, canal, sucursal, categoría o segmento."

    dim = DIMENSIONES.get(intencion.dimension) if intencion.dimension else None
    dcol = intencion.dimension

    if op == "comparacion_periodos":
        base, act = intencion.periodo_comparacion, intencion.periodo
        if not dim:
            fila = filas[0]
            if fila.get("valor_base") is None or fila.get("valor_actual") is None:
                falta = base if fila.get("valor_base") is None else act
                resumen = (f"{m.nombre}{con_filtros}: no hay registros en {falta}, por lo que no se puede calcular la variación "
                           f"(no se asume cero). Valor disponible: "
                           f"{fmt(fila.get('valor_actual') if fila.get('valor_actual') is not None else fila.get('valor_base'), f)}.")
                return resumen, ""
            resumen = (f"{m.nombre}{con_filtros}: **{fmt(fila['valor_actual'], f)}** en {act} frente a "
                       f"{fmt(fila['valor_base'], f)} en {base} ({fmt(fila['variacion'], formato_columna('variacion', intencion.metrica))}; "
                       f"{fmt(fila['variacion_pct'], 'pct')}).")
            dur = ("Periodos de igual duración." if abs(act.dias - base.dias) <= 3 else
                   f"Atención: los periodos tienen distinta duración ({act.dias} vs {base.dias} días).")
            return resumen, dur
        completas = [r for r in filas if r.get("variacion") is not None]
        primero = completas[0] if completas else filas[0]
        reduce = intencion.orden == "asc"
        var = primero.get("variacion")
        if reduce and var is not None and var > 0:
            titular = (f"Ningún(a) {dim.nombre.lower()} redujo su {m.nombre.lower()}; el de menor crecimiento fue "
                       f"**{primero[dcol]}**")
        elif not reduce and var is not None and var < 0:
            titular = f"Ningún(a) {dim.nombre.lower()} creció; la menor caída fue de **{primero[dcol]}**"
        else:
            titular = (f"{dim.nombre} con mayor {'reducción' if reduce else 'crecimiento'} de {m.nombre.lower()}: "
                       f"**{primero[dcol]}**")
        resumen = (f"{titular} — {fmt(primero['valor_base'], f)} en {base} → {fmt(primero['valor_actual'], f)} en {act} "
                   f"({fmt(var, formato_columna('variacion', intencion.metrica))}; {fmt(primero.get('variacion_pct'), 'pct')}){con_filtros}.")
        caen = [r[dcol] for r in filas if (r.get("variacion") or 0) < 0]
        suben = [r[dcol] for r in filas if (r.get("variacion") or 0) > 0]
        interp = f"{len(caen)} de {len(filas)} grupos disminuyeron y {len(suben)} aumentaron. "
        if abs(act.dias - base.dias) <= 3:
            interp += "Se comparan periodos de igual duración, lo que neutraliza la estacionalidad."
        else:
            interp += (f"Atención: los periodos tienen distinta duración ({act.dias} vs {base.dias} días); la variación "
                       f"refleja también esa diferencia.")
        if intencion.dimension == "segmento":
            interp += (" El segmento se toma vigente a la fecha de cada compra (SCD Tipo 2), por lo que las "
                       "reclasificaciones de clientes no distorsionan la historia.")
        return resumen, interp

    if op == "comparacion_miembros":
        totales = [r for r in filas if not intencion.desglose or r.get(intencion.desglose) == "Total periodo"]
        partes = []
        for r in totales:
            extra = ""
            for c in ("margen_pct", "margen_bruto", "transacciones", "ingreso_neto"):
                if c in r and c != intencion.metrica:
                    extra = f" ({METRICAS[c].nombre.lower()} {fmt(r[c], METRICAS[c].formato)})"
                    break
            partes.append(f"**{r[dcol]}**: {fmt(r[intencion.metrica], f)}{extra}")
        resumen = f"{m.nombre} en {per}{con_filtros}: " + " vs ".join(partes) + "."
        interp = ""
        if len(totales) >= 2 and all(isinstance(r[intencion.metrica], (int, float)) for r in totales[:2]):
            a, b = sorted(totales, key=lambda r: r[intencion.metrica], reverse=True)[:2]
            dif = a[intencion.metrica] - b[intencion.metrica]
            interp = (f"{a[dcol]} supera a {b[dcol]} por {fmt(dif, 'pp' if f == 'pct' else f)} en el periodo. ")
            if intencion.desglose:
                meses = [r for r in filas if r.get(intencion.desglose) != "Total periodo"]
                gana = {}
                for r in meses:
                    k = r[intencion.desglose]
                    if k not in gana or r[intencion.metrica] > gana[k][1]:
                        gana[k] = (r[dcol], r[intencion.metrica])
                n_a = sum(1 for v in gana.values() if v[0] == a[dcol])
                interp += f"Lideró en {n_a} de {len(gana)} meses del periodo."
        if "pct" not in intencion.metrica and intencion.metrica == "margen_bruto":
            interp += " El margen % permite comparar canales de distinto tamaño."
        return resumen, interp.strip()

    if op == "tendencia":
        vals = [(r[dcol], r[intencion.metrica]) for r in filas if r[intencion.metrica] is not None]
        mx = max(vals, key=lambda x: x[1])
        mn = min(vals, key=lambda x: x[1])
        resumen = (f"{m.nombre} por {dim.nombre.lower()}{con_filtros} en {per}: {len(vals)} periodos; "
                   f"máximo **{mx[0]}** ({fmt(mx[1], f)}) y mínimo **{mn[0]}** ({fmt(mn[1], f)}).")
        if m.aditividad == "aditiva":
            resumen += f" Total del periodo: {fmt(sum(v for _, v in vals), f)}."
        primero, ultimo = vals[0], vals[-1]
        interp = (f"Entre {primero[0]} y {ultimo[0]} la métrica pasó de {fmt(primero[1], f)} a {fmt(ultimo[1], f)}"
                  f" ({fmt((ultimo[1] / primero[1] - 1) * 100 if primero[1] else None, 'pct')}).")
        if filas[-1].get("variacion_pct") is not None:
            interp += f" El último periodo varió {fmt(filas[-1]['variacion_pct'], 'pct')} respecto al anterior."
        return resumen, interp

    # ranking
    criterio = "mayor" if intencion.orden == "desc" else "menor"
    top = filas[0]
    part = f", {fmt(top['participacion_pct'], 'pct')} del total" if top.get("participacion_pct") is not None else ""
    ctx = ""
    for c in ("transacciones", "margen_pct", "ingreso_neto", "descuento"):
        if c in top and c != intencion.metrica:
            ctx = f"; {METRICAS[c].nombre.lower()}: {fmt(top[c], METRICAS[c].formato)}"
            break
    if intencion.limite == 1 or len(filas) == 1:
        resumen = (f"{dim.nombre} con {criterio} {m.nombre.lower()}{con_filtros} en {per}: **{top[dcol]}** "
                   f"({fmt(top[intencion.metrica], f)}{part}{ctx}).")
    else:
        items = [f"{i}) {r[dcol]} ({fmt(r[intencion.metrica], f)})" for i, r in enumerate(filas[:10], 1)]
        resumen = (f"{len(filas)} {dim.nombre.lower()}(s) con {criterio} {m.nombre.lower()}{con_filtros} en {per}: "
                   + "; ".join(items) + ".")
    interp = ""
    if len(filas) >= 2 and isinstance(filas[1][intencion.metrica], (int, float)) and filas[1][intencion.metrica]:
        brecha = (top[intencion.metrica] / filas[1][intencion.metrica] - 1) * 100
        interp = (f"{top[dcol]} {'supera' if intencion.orden == 'desc' else 'queda por debajo de'} a {filas[1][dcol]} "
                  f"en {fmt(abs(brecha), 'pct')}. ")
    if top.get("participacion_pct") is not None and len(filas) >= 3:
        conc = sum(r["participacion_pct"] or 0 for r in filas[:3])
        interp += f"Los tres primeros concentran {fmt(conc, 'pct')} del total del periodo."
        if intencion.limite and len(filas) > 3:
            tot = sum(r["participacion_pct"] or 0 for r in filas)
            interp += f" Los {len(filas)} mostrados suman {fmt(tot, 'pct')} del total."
    elif intencion.limite == 1 and top.get("participacion_pct") is not None:
        interp += f"Representa {fmt(top['participacion_pct'], 'pct')} del total del periodo."
    return resumen, interp.strip()


# ------------------------------------------------------------------------------------ presentación
def presentar(respuesta, usuario=None, incluir_tabla: bool = True) -> str:
    """Markdown de la respuesta. El nivel de detalle depende del tipo de usuario (polimorfismo)."""
    tecnico = usuario.muestra_sql() if usuario is not None else True
    partes = [respuesta.resumen]
    if respuesta.tipo in ("RESPUESTA",):
        if respuesta.interpretacion:
            partes.append(f"**Interpretación gerencial:** {respuesta.interpretacion}")
        if incluir_tabla and respuesta.resultado is not None and respuesta.resultado.n_filas > 1:
            partes.append(tabla_markdown(respuesta.resultado, _metrica_de(respuesta)))
        ev = [f"- **Métrica:** {respuesta.metrica} — {respuesta.regla_calculo}",
              f"- **Periodo:** {respuesta.periodo}",
              f"- **Filtros:** {respuesta.filtros or 'ninguno'}",
              f"- **Dimensión:** {respuesta.dimension or '— (total)'}",
              f"- **Fuente:** " + ", ".join(f.tabla for f in respuesta.fuentes) + f" · consulta {respuesta.consulta_codigo}"]
        partes.append("**Evidencia**\n" + "\n".join(ev))
        if tecnico and respuesta.sql:
            partes.append(f"```sql\n{respuesta.sql}\n```\nParámetros: `{respuesta.parametros}`")
    if respuesta.opciones:
        partes.append("**Opciones:** " + " · ".join(_nombre_opcion(o) for o in respuesta.opciones))
    if respuesta.advertencias:
        partes.append("**Advertencias**\n" + "\n".join(f"- {a}" for a in respuesta.advertencias))
    return "\n\n".join(partes)


def _metrica_de(respuesta):
    for codigo, m in METRICAS.items():
        if m.nombre == respuesta.metrica:
            return codigo
    return None


def _nombre_opcion(o: str) -> str:
    return METRICAS[o].nombre if o in METRICAS else str(o)
