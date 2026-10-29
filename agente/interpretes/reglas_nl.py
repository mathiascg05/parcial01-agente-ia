"""
Intérprete por reglas (sin LLM). Respaldo determinista: funciona sin internet ni API key.

Pasos: limpiar texto -> detectar operación prohibida / fuera de alcance -> valores de filtro conocidos
-> métrica -> periodos -> dimensión (y dimensiones inexistentes) -> operación, orden y límite
-> ambigüedad / parámetros faltantes. Produce el diccionario del esquema común (ver base.py).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from agente.catalogo import (CRITERIOS_AMBIGUEDAD, DIMENSIONES_NO_DISPONIBLES, TEMAS_FUERA_DE_ALCANCE)
from agente.datamart import normalizar
from agente.interpretes.base import InterpreteBase, intencion_a_datos

NUMEROS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
           "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20}
MESES_NOMBRE = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun", 7: "jul", 8: "ago", 9: "sep", 10: "oct",
                11: "nov", 12: "dic"}
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
ORDINALES = {"primer": 1, "primero": 1, "1er": 1, "1": 1, "segundo": 2, "2do": 2, "2": 2, "tercer": 3, "tercero": 3,
             "3er": 3, "3": 3, "cuarto": 4, "4to": 4, "4": 4}
NUM = r"(\d+|" + "|".join(NUMEROS) + r")"

# Métricas: (patrón, código). Se evalúan en orden de especificidad.
METRICAS_PATRONES = [
    (r"margen (bruto )?(porcentual|en porcentaje|%)|(porcentaje|%) de margen|margen pct|rentabilidad porcentual", "margen_pct"),
    (r"ticket promedio|ticket medio|valor promedio (por|de) (compra|ticket|venta)|gasto promedio|compra promedio", "ticket_promedio"),
    (r"(porcentaje|%|tasa) de descuento|descuento (porcentual|promedio|%)", "descuento_pct"),
    (r"margen|ganancia|utilidad|rentabilidad|rentable|rentables", "margen_bruto"),
    (r"descuentos?|rebajas?", "descuento"),
    (r"costos?|coste", "costo"),
    (r"clientes activos|numero de clientes|cantidad de clientes|cuantos clientes", "clientes_activos"),
    (r"transacciones|numero de (ventas|tickets|compras)|cantidad de (ventas|tickets|compras)|cuantas (ventas|compras)|cuantos tickets|tickets", "transacciones"),
    (r"unidades|cantidad vendida|cantidades|piezas|mas vendid[oa]s?|volumen de unidades", "unidades"),
    (r"ventas? brutas?|monto bruto|ingresos? brutos?", "monto_bruto"),
    (r"ingresos? netos?|ingresos?|ventas?|facturacion|facturad[oa]|monto vendido|vend(?:e|en|emos|imos|io|ieron|ido|ida|imos)|compr(?:a|as|an|o|aron|amos|ado|ada)|factur\w*|volumen de (compra|ventas?)|valor de (las )?ventas", "ingreso_neto"),
]

# Dimensiones: (patrón, código). Las temporales requieren una construcción explícita ("por mes", "mensual").
DIMENSIONES_PATRONES = [
    (r"\bdiasemana\b", "dia_semana"),
    (r"\btipo de dia\b|\bfin de semana (vs|o|contra) entre semana\b", "tipo_dia"),
    (r"\btipocliente\b", "tipo_cliente"),
    (r"\btipocanal\b", "tipo_canal"),
    (r"\bsubcategorias?\b", "subcategoria"),
    (r"\bcategorias?\b", "categoria"),
    (r"\bsegmentos?\b", "segmento"),
    (r"\b(productos?|articulos?|items?)\b", "producto"),
    (r"\bmarcas?\b", "marca"),
    (r"\bclientes?\b", "cliente"),
    (r"\b(sucursal|sucursales|sedes?|tiendas?)\b", "sucursal"),
    (r"\bciudad(es)? (del|de los) clientes?\b", "ciudad_cliente"),
    (r"\bciudad(es)?\b", "ciudad"),
    (r"\b(region|regiones|zonas?)\b", "region"),
    (r"\b(por|cada|que|cual) estados?\b|\bestados del pais\b", "estado"),
    (r"\bcanal(es)?\b", "canal"),
    (r"\b(por|cada|que|cual|cuales|del?|el) (mes|meses)\b|\bmensual(es|mente)?\b|\bmes a mes\b|\bmes(es)? con\b", "mes"),
    (r"\b(por|cada|que|cual|cuales) trimestres?\b|\btrimestral(es)?\b|\btrimestres? con\b|\btrimestre a trimestre\b", "trimestre"),
    (r"\b(por|cada|que|cual) semestres?\b|\bsemestral(es)?\b", "semestre"),
    (r"\b(por|cada|que|cual) (ano|anos)\b|\banual(es|mente)?\b|\bano a ano\b|\bano con\b", "anio"),
]

# Alias de valores frecuentes (texto normalizado -> (dimensión, valor canónico))
ALIAS_VALORES = {
    "tienda fisica": ("canal", "Tienda física"), "fisica": ("canal", "Tienda física"),
    "ecommerce": ("canal", "E-commerce web"), "e commerce": ("canal", "E-commerce web"),
    "comercio electronico": ("canal", "E-commerce web"), "pagina web": ("canal", "E-commerce web"),
    "web": ("canal", "E-commerce web"), "online": ("canal", "E-commerce web"),
    "app": ("canal", "App móvil"), "aplicacion": ("canal", "App móvil"), "app movil": ("canal", "App móvil"),
    "whatsapp": ("canal", "Delivery WhatsApp"), "delivery": ("canal", "Delivery WhatsApp"),
    "mayorista": ("canal", "Mayorista B2B"), "b2b": ("canal", "Mayorista B2B"), "al mayor": ("canal", "Mayorista B2B"),
    "digital": ("tipo_canal", "Digital"), "digitales": ("tipo_canal", "Digital"), "presencial": ("tipo_canal", "Presencial"),
    "presenciales": ("tipo_canal", "Presencial"),
    "corporativos": ("segmento", "Corporativo"), "premiums": ("segmento", "Premium"),
    "frecuentes": ("segmento", "Frecuente"), "minoristas": ("segmento", "Minorista"),
    "fin de semana": ("tipo_dia", "Fin de semana"), "fines de semana": ("tipo_dia", "Fin de semana"),
    "entre semana": ("tipo_dia", "Entre semana"), "dias de semana": ("tipo_dia", "Entre semana"),
    "dias habiles": ("tipo_dia", "Entre semana"), "dias laborables": ("tipo_dia", "Entre semana"),
    "naturales": ("tipo_cliente", "Natural"), "persona natural": ("tipo_cliente", "Natural"),
    "juridicos": ("tipo_cliente", "Jurídico"), "empresas": ("tipo_cliente", "Jurídico"),
}

# Para valores ambiguos entre dimensiones, prioridad de resolución
PRIORIDAD_DIM = ["canal", "segmento", "categoria", "subcategoria", "sucursal", "region", "ciudad", "estado",
                 "tipo_canal", "tipo_cliente", "tipo_dia", "marca", "producto", "cliente"]

SUPERLATIVOS = r"\b(mejor|mejores|peor|peores|destaca\w*|mas importantes?|lider\w*|top|principal(es)?|mas exitos\w*|" \
               r"desempeno|rinde|rindio|rendimiento|resultados?|ganador\w*)\b"
MAYOR = r"\b(mayor|mayores|mas alt[oa]s?|maxim[oa]s?|mas grandes?|lidera\w*|encabez\w*|concentra\w*|primer lugar|mejor|mejores|top)\b|\bmas\b"
MENOR = r"\b(menor|menores|menos|mas baj[oa]s?|baj[oa]s?|minim[oa]s?|peor|peores|inferior\w*|ultimo lugar)\b"
REDUCCION = r"\b(redu\w*|disminu\w*|cay\w*|caida|bajo su|bajaron|perdi\w*|contraj\w*|empeor\w*|retroced\w*)\b"
CRECIMIENTO = r"\b(crec\w*|aument\w*|increment\w*|mejoro|subio|subieron|expandi\w*)\b"
VARIACION = r"\b(variacion|vario|variaron|cambio)\b"
TENDENCIA = r"\b(evolucion\w*|evoluciono|tendencia|comportamiento|historico|trayectoria)\b"
COMPARAR = r"\b(compar\w*|vs|versus|frente a|contra|respecto (a|de)|con respecto)\b"
STOP_POR = {"favor", "ciento", "que", "ejemplo", "lo", "el", "la", "los", "las", "un", "una", "encima", "debajo",
            "separado", "completo", "dia", "fecha", "periodo", "ultimo", "tanto", "otro", "otra", "cierto", "eso",
            "esto", "cada", "vendidas", "vendidos", "vendida", "vendido", "netas", "netos", "brutas", "brutos",
            "separado", "ultimos", "ultimas", "encima", "debajo", "parte", "lo", "tanto", "si", "mucho", "poco"}

_VACIO = " "
TEMAS_REGEX = [
    (r"\banul\w+|\bcancelad\w*", "El Data Mart sólo contiene ventas completadas: los tickets anulados se excluyen en el ETL "
                                 "(quedan en la auditoría control.etl_rechazo, que el agente no consulta)."),
    (r"\bproyect\w+|\bpronostic\w+|\bpredic\w+|\bestim(ar|acion|ado) (de )?(las )?ventas futuras",
     "El Data Mart sólo contiene datos históricos (ene-2025 a sep-2026); el agente no hace proyecciones."),
    (r"\bdevol\w+|\breembols\w+", "El Data Mart de ventas no registra devoluciones."),
]
PALABRAS_NO_VALOR = {"con", "que", "mas", "menos", "mayor", "menor", "por", "del", "las", "los", "una", "uno", "durante",
                     "entre", "segun", "cada", "tuvo", "tiene", "tienen", "fue", "fueron", "genero", "vende", "vendio",
                     "presenta", "concentra", "lidera", "redujo", "crecio", "registro", "obtuvo", "aporta", "aporto",
                     "hay", "mejor", "peor", "este", "esta", "ese", "esa", "para", "sin", "son", "era", "ano", "mes",
                     "trimestre", "semestre", "ultimo", "ultimos", "ultima", "ultimas", "primer", "segundo", "tercer",
                     "cuarto", "periodo", "determinado", "determinada", "especifico", "especifica", "dado", "dada",
                     "ventas", "venta", "ingreso", "ingresos", "margen", "ticket", "promedio", "clientes", "cliente",
                     "productos", "producto", "neto", "bruto", "descuento", "costo", "unidades", "desde", "hasta",
                     "contra", "versus", "frente", "respecto", "total", "totales", "general", "completo", "actual",
                     "anterior", "pasado", "cual", "cuales", "como", "donde", "cuando", "cuanto", "cuantos",
                     "aumento", "aumentaron", "disminuyo", "cayo", "gano", "perdio", "mejoro", "empeoro", "subio",
                     "bajo", "vendieron", "compro", "compraron", "genera", "generan", "rinde", "rindio", "fue"}
VOCABULARIO_METRICAS = {"ingreso": "ingreso_neto", "ingresos": "ingreso_neto", "ventas": "ingreso_neto",
                        "facturacion": "ingreso_neto", "margen": "margen_bruto", "ganancia": "margen_bruto",
                        "ganancias": "margen_bruto", "utilidad": "margen_bruto", "rentabilidad": "margen_bruto",
                        "descuento": "descuento", "descuentos": "descuento", "costo": "costo", "costos": "costo",
                        "unidades": "unidades", "transacciones": "transacciones", "tickets": "transacciones"}


def _capitalizada(original: str, palabra: str) -> bool:
    """¿El usuario escribió la palabra con mayúscula inicial? (indicio de nombre propio: «canal Instagram»)."""
    import unicodedata
    sin_acentos = unicodedata.normalize("NFKD", original).encode("ascii", "ignore").decode("ascii")
    m = re.search(rf"\b{re.escape(palabra)}\b", sin_acentos, re.I)
    return bool(m) and m.group(0)[0].isupper()


class InterpreteReglas(InterpreteBase):
    nombre = "reglas"

    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def limpiar(texto: str) -> str:
        t = normalizar(texto)
        t = re.sub(r"[¿?¡!,;:()\"'“”]", " ", t)
        t = t.replace(" n ", " ")
        # canonizaciones de frases compuestas
        reemplazos = [
            (r"segmentos? de (los |sus )?clientes?", "segmento"), (r"tipos? de clientes?", "tipocliente"),
            (r"tipos? de canal(es)?", "tipocanal"), (r"dias? de la semana", "diasemana"),
            (r"\bano\b|\banio\b", "ano"), (r"\baño\b", "ano"),
            (r"\bq([1-4])\b", r"t\1"), (r"\btrim\b", "trimestre"), (r"\bx\b", "por"),
        ]
        for a, b in reemplazos:
            t = re.sub(a, b, t)
        return " ".join(t.split())

    def interpretar(self, texto: str, meta, contexto: dict | None = None) -> dict:
        t = self.limpiar(texto)
        datos: dict = {"tipo": "consulta", "filtros": [], "supuestos": []}

        seguimiento = re.match(r"^(y|e|tambien|ahora)\b", t) is not None
        previa = (contexto or {}).get("ultima_intencion") if seguimiento else None

        # 1) Fuera de alcance por tema (antes que cualquier otra cosa)
        for tema in TEMAS_FUERA_DE_ALCANCE:
            if re.search(rf"\b{re.escape(tema)}\b", t):
                return {"tipo": "fuera_de_alcance",
                        "motivo": f"El Data Mart de ventas no contiene información sobre '{tema}'."}
        for patron, motivo in TEMAS_REGEX:
            if re.search(patron, t):
                return {"tipo": "fuera_de_alcance", "motivo": motivo}

        # 2) Valores de filtro conocidos (se eliminan del texto para no confundirlos con dimensiones)
        filtros, t_sin_valores = self._valores(t, meta)
        if self._clientes_ambiguos and not any(f["dimension"] == "cliente" for f in filtros):
            nombre, vals = self._clientes_ambiguos[0]
            return {"tipo": "faltan_parametros", "faltantes": ["cliente"], "dimension": "cliente", "opciones": vals[:12],
                    "motivo": f"Hay {len(vals)} clientes distintos con el nombre «{nombre.title()}». Indique cuál con su "
                              f"código (p. ej. {vals[0].split('(')[-1].rstrip(')')}); no se suman clientes diferentes."}

        # 2b) Valores NO reconocidos tras el nombre de una dimensión ("el canal Instagram"): se pasan como filtro
        #     para que la regla RV05 los rechace con sugerencias, en vez de ignorarlos en silencio.
        dims_con_valor = {f["dimension"] for f in filtros}
        for m in re.finditer(r"\b(canal|categoria|subcategoria|sucursal|segmento|region|marca|ciudad|estado)\s+"
                             r"([a-z0-9][a-z0-9]{2,})\b", t_sin_valores):
            dim, palabra = m.group(1), m.group(2)
            if dim in dims_con_valor or palabra in PALABRAS_NO_VALOR or palabra.isdigit() \
                    or not _capitalizada(texto, palabra):
                continue
            filtros.append({"dimension": dim, "valores": [palabra]})
            t_sin_valores = t_sin_valores.replace(m.group(0), " ")

        # 3) Métrica
        metrica, t_resto = None, t_sin_valores
        for patron, codigo in METRICAS_PATRONES:
            m = re.search(rf"(?<!\w)(?:{patron})(?!\w)", t_resto)
            if m:
                metrica = codigo
                t_resto = t_resto[:m.start()] + _VACIO + t_resto[m.end():]
                break
        if metrica is None:      # tolerancia a errores de tipeo ("ingrezo", "margn")
            import difflib
            for palabra in t_resto.split():
                if len(palabra) >= 5:
                    cerca = difflib.get_close_matches(palabra, list(VOCABULARIO_METRICAS), n=1, cutoff=0.8)
                    if cerca:
                        metrica = VOCABULARIO_METRICAS[cerca[0]]
                        datos["supuestos"].append(f"Se interpretó «{palabra}» como «{cerca[0]}».")
                        t_resto = re.sub(rf"\b{re.escape(palabra)}\b", " ", t_resto, count=1)
                        break
        if metrica == "margen_bruto" and re.search(MENOR, t) and not re.search(r"margen bruto|en (usd|dolares)", t):
            metrica = "margen_pct"
            datos["supuestos"].append("«Peor/menor margen» se evaluó con el margen % (comparable entre grupos de distinto tamaño "
                                      "o con ventas en sólo parte del periodo).")
        if metrica == "ingreso_neto" and re.search(r"volumen de compra", t):
            datos["supuestos"].append("'Volumen de compra' se midió como ingreso neto (USD); también puede "
                                      "consultarse en unidades.")
        if metrica == "margen_bruto" and re.search(r"\brentab", t):
            datos["supuestos"].append("'Rentabilidad' se midió como margen bruto en USD (también existe margen %).")

        # 3b) En seguimientos: "el periodo/los meses anteriores" se calcula contra el periodo de la pregunta anterior
        desplazar = None
        if previa is not None and previa.periodo is not None:
            md = re.search(rf"\b(?:(?:los|las|el|la) )?(?:{NUM} )?(periodo|mes|meses|trimestre|trimestres|semestre|ano) anterior(?:es)?\b", t_resto)
            if md:
                desplazar = md.group(0)
                t_resto = t_resto.replace(md.group(0), " ")
        ordinal = re.match(r"^(?:y )?(?:el |la |y el |y la )?(segund|tercer|cuart|quint)[oa]?s?$", t.strip()) if previa is not None else None
        # 4) Periodos ("el mismo trimestre de 2025" se resuelve contra la pregunta anterior)
        mismo = re.search(r"\b(?:el |la )?mism[oa] (trimestre|mes|periodo|semestre|ano|lapso) (?:de |del )?(?:ano )?(20\d\d)\b", t_resto)
        if mismo:
            t_resto = t_resto.replace(mismo.group(0), " ")
        periodos, t_resto = self._periodos(t_resto, meta)
        hay_comparar_txt = re.search(COMPARAR, t) is not None or re.search(VARIACION, t) is not None
        # Varios meses sin comparación explícita ("marzo, abril y mayo de 2026") = un solo rango
        if len(periodos) >= 2 and not hay_comparar_txt and not re.search(CRECIMIENTO, t) and not re.search(REDUCCION, t) \
                and all(p.get("tipo") == "mes" for p in periodos):
            anios = {p.get("anio") for p in periodos}
            nums = sorted(p["numero"] for p in periodos)
            if len(anios) == 1 and nums == list(range(nums[0], nums[-1] + 1)):
                anio = anios.pop() or (meta.fecha_max.year if nums[-1] <= meta.fecha_max.month else meta.fecha_max.year - 1)
                periodos = [{"tipo": "rango", "desde": f"{anio}-{nums[0]:02d}", "hasta": f"{anio}-{nums[-1]:02d}"}]

        # 4b) Tolerancia a errores de tipeo en la dimensión ("por regoin")
        import difflib
        palabras_dim = ["region", "categoria", "subcategoria", "sucursal", "canal", "segmento", "producto", "marca",
                        "ciudad", "cliente", "estado", "trimestre", "semestre", "regiones", "categorias", "sucursales",
                        "canales", "segmentos", "productos", "marcas", "ciudades", "clientes"]
        for mp in re.finditer(r"\b(por|cada|que|cual)\s+([a-z]{4,})\b", t_resto):
            w = mp.group(2)
            if w not in palabras_dim and w not in STOP_POR and w not in DIMENSIONES_NO_DISPONIBLES \
                    and w not in ("tipocliente", "tipocanal", "diasemana") and not any(re.search(p_, w) for p_, _ in DIMENSIONES_PATRONES):
                cerca = difflib.get_close_matches(w, palabras_dim, n=1, cutoff=0.75)
                if cerca:
                    t_resto = t_resto.replace(w, cerca[0], 1)
                    datos["supuestos"].append(f"Se interpretó «{w}» como «{cerca[0]}».")

        # 5) Dimensiones inexistentes ("por vendedor", "qué proveedor")
        inexistente = self._dimension_inexistente(t_resto)
        if inexistente:
            return {"tipo": "dimension_inexistente", "dimension_texto": inexistente, "metrica": metrica,
                    "motivo": f"El Data Mart no tiene la dimensión '{inexistente}'."}

        # 6) Dimensión de agrupación
        dimension = self._dimension(t_resto, filtros)

        # 7) Operación, orden y límite
        orden = "asc" if re.search(MENOR, t) or re.search(REDUCCION, t) else "desc"
        operacion = "ranking" if dimension else "total"
        dims_filtro = {}
        for f in filtros:
            dims_filtro.setdefault(f["dimension"], []).extend(f["valores"])

        if re.search(TENDENCIA, t) and (dimension is None or dimension in ("mes", "trimestre", "anio", "semestre")):
            dimension = dimension or "mes"
        temporal = dimension in ("mes", "trimestre", "anio", "semestre")
        hay_comparar = re.search(COMPARAR, t) is not None
        multi = [d for d, v in dims_filtro.items() if len(v) >= 2]
        if len(periodos) >= 2 and periodos[0].get("tipo") in ("semestre", "trimestre", "mes") \
                and periodos[1].get("tipo") == "anio" and periodos[0].get("numero"):
            # "el primer semestre de 2026 frente al de 2025": el segundo periodo es el mismo tramo del otro año
            periodos[1] = {**periodos[0], "anio": periodos[1]["anio"]}
        if len(periodos) >= 2 and (hay_comparar or re.search(VARIACION, t) or re.search(CRECIMIENTO, t)
                                   or re.search(REDUCCION, t) or " y " in f" {t} "):
            operacion = "comparacion_periodos"
            datos["periodo"], datos["periodo_comparacion"] = periodos[0], periodos[1]
        elif (re.search(REDUCCION, t) or re.search(CRECIMIENTO, t) or re.search(VARIACION, t)) and not temporal:
            operacion = "comparacion_periodos"
            datos["periodo"] = periodos[0] if periodos else None
        elif multi and (hay_comparar or dimension in (None, multi[0])):
            operacion = "comparacion_miembros"
            dimension = multi[0]
            if dimension not in ("producto",):
                datos["desglose"] = "mes" if (periodos and periodos[0].get("tipo") in ("ultimos_meses", "trimestre",
                                                                                         "rango", "semestre")) \
                    or re.search(r"\b(por mes|mensual\w*|mes a mes)\b", t) else None
            datos["periodo"] = periodos[0] if periodos else None
        else:
            datos["periodo"] = periodos[0] if periodos else None
            if dimension and dimension in ("mes", "trimestre", "anio", "semestre") \
                    and not re.search(MAYOR, t) and not re.search(MENOR, t):
                operacion = "tendencia"

        if operacion == "comparacion_periodos":
            orden = "asc" if re.search(REDUCCION, t) or re.search(MENOR, t) else "desc"

        # Comparación de miembros sin especificar cuáles ("compare dos canales")
        m_dos = re.search(rf"\b(compar\w*)\b.*\b{NUM} (canales|categorias|sucursales|segmentos|regiones|productos)\b", t)
        if m_dos and operacion != "comparacion_miembros" and not multi:
            dim_map = {"canales": "canal", "categorias": "categoria", "sucursales": "sucursal",
                       "segmentos": "segmento", "regiones": "region", "productos": "producto"}
            dim = dim_map[m_dos.group(3)]
            return {"tipo": "faltan_parametros", "metrica": metrica, "dimension": dim, "faltantes": [dim],
                    "opciones": meta.opciones(dim),
                    "motivo": f"Indique cuáles {m_dos.group(3)} desea comparar (p. ej. "
                              f"'{' y '.join(meta.opciones(dim, 2))}')."}

        limite = self._limite(t_resto, dimension, operacion, t)

        # "dentro de una categoría y periodo determinados" sin valores concretos
        faltantes = []
        for dim_txt, dim_cod in [("categoria", "categoria"), ("sucursal", "sucursal"), ("canal", "canal"),
                                 ("segmento", "segmento"), ("region", "region")]:
            if re.search(rf"\b(una|cierta|determinad[ao]|alguna|cualquier)\s+{dim_txt}\b|\b{dim_txt}\s+(determinad[ao]|especific[ao]|dad[ao])", t) \
                    and dim_cod not in dims_filtro:
                faltantes.append(dim_cod)
        if re.search(r"\bperiodos? (determinad\w*|especific\w*|dad\w*)\b|\b(un|cierto|determinado) periodo\b", t) and not periodos:
            faltantes.append("periodo")
        if faltantes:
            opciones = [] if faltantes == ["periodo"] else meta.opciones(faltantes[0])
            return {"tipo": "faltan_parametros", "metrica": metrica, "dimension": dimension, "faltantes": faltantes,
                    "opciones": opciones,
                    "motivo": "La pregunta deja abiertos parámetros que cambian el resultado: indique "
                              + " y ".join({"periodo": "el periodo", "categoria": "la categoría", "sucursal": "la sucursal",
                                            "region": "la región", "canal": "el canal", "segmento": "el segmento"}[f]
                                           for f in faltantes) + "."}

        # 8) Seguimiento: completar con la intención previa de la sesión
        if previa is not None:
            base = intencion_a_datos(previa)
            nuevos_filtros = {f["dimension"]: f for f in base.get("filtros", [])}
            for f in filtros:
                nuevos_filtros[f["dimension"]] = f
            base.update({k: v for k, v in {"metrica": metrica, "dimension": dimension}.items() if v})
            if periodos:
                base["periodo"] = periodos[0]
                base["periodo_comparacion"] = periodos[1] if len(periodos) > 1 else base.get("periodo_comparacion")
            base["filtros"] = list(nuevos_filtros.values())
            base["supuestos"] = ["Pregunta de seguimiento: se reutilizó el contexto de la pregunta anterior de la sesión."]
            if (hay_comparar or mismo) and previa.periodo is not None:
                p0 = previa.periodo
                base["operacion"] = "comparacion_periodos"
                base["periodo"] = {"tipo": "rango", "desde": p0.desde.isoformat(), "hasta": p0.hasta.isoformat()}
                if mismo:
                    anio = int(mismo.group(2))
                    dy = anio - p0.desde.year
                    try:
                        base["periodo_comparacion"] = {"tipo": "rango", "desde": p0.desde.replace(year=p0.desde.year + dy).isoformat(),
                                                       "hasta": p0.hasta.replace(year=p0.hasta.year + dy).isoformat()}
                    except ValueError:
                        base["periodo_comparacion"] = {"tipo": "anio", "anio": anio}
                elif periodos:
                    base["periodo_comparacion"] = periodos[0]
                else:
                    base["periodo_comparacion"] = None
            if dimension and dimension != previa.dimension and previa.operacion not in ("comparacion_periodos",):
                base["operacion"] = "tendencia" if dimension in ("mes", "trimestre", "anio") else "ranking"
            if desplazar and previa.periodo is not None:
                p0 = previa.periodo
                meses = (p0.hasta.year * 12 + p0.hasta.month) - (p0.desde.year * 12 + p0.desde.month) + 1
                y, m = p0.desde.year, p0.desde.month - meses
                while m < 1:
                    m += 12
                    y -= 1
                fin = date(p0.desde.year, p0.desde.month, 1) - timedelta(days=1)
                base["periodo"] = {"tipo": "rango", "desde": f"{y}-{m:02d}", "hasta": fin.isoformat()}
                if base.get("operacion") == "comparacion_periodos":
                    base["periodo_comparacion"] = None
                base["supuestos"].append(f"«{desplazar.strip()}» se calculó respecto del periodo de la pregunta anterior ({p0}).")
            if ordinal and previa.limite:
                n = {"segund": 2, "tercer": 3, "cuart": 4, "quint": 5}[ordinal.group(1)]
                base["limite"] = n
                base["supuestos"].append(f"Se muestran los {n} primeros: el lugar {n} es la última fila.")
            return base

        # 9) Ambigüedad / alcance
        if metrica is None:
            hay_superlativo = re.search(SUPERLATIVOS, t) or re.search(MAYOR, t) or re.search(MENOR, t)
            if dimension or hay_superlativo or filtros:
                return {"tipo": "ambigua", "dimension": dimension, "opciones": CRITERIOS_AMBIGUEDAD,
                        "motivo": "La pregunta no indica el criterio de evaluación. Puede medirse por ingreso neto, "
                                  "margen bruto, cantidad vendida (unidades) o ticket promedio."}
            return {"tipo": "fuera_de_alcance",
                    "motivo": "No se reconoce una métrica ni una dimensión del Data Mart de ventas en la pregunta."}

        datos.update({"operacion": operacion, "metrica": metrica, "dimension": dimension, "filtros": filtros,
                      "orden": orden, "limite": limite})
        datos.setdefault("periodo", None)
        return datos

    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def _indice_clientes(meta) -> tuple[dict, dict]:
        """id normalizado -> valor, y nombre normalizado (con y sin 'c.a.') -> [valores]. Se cachea en meta."""
        if getattr(meta, "_idx_clientes", None) is None:
            por_id, por_nombre = {}, {}
            for v in meta.valores.get("cliente", []):
                m = re.match(r"^(.*) \((C\d+)\)$", v)
                if not m:
                    continue
                por_id[m.group(2).lower()] = v
                nombre = normalizar(m.group(1))
                for clave in {nombre, re.sub(r"\s*c\.?\s?a\.?$", "", nombre).strip()}:
                    if len(clave) >= 8:
                        por_nombre.setdefault(clave, []).append(v)
            meta._idx_clientes = (por_id, por_nombre)
        return meta._idx_clientes

    def _valores(self, t: str, meta) -> tuple[list[dict], str]:
        """Encuentra valores de dimensiones (categorías, canales, sucursales...) mencionados en el texto."""
        candidatos = []   # (inicio, fin, dimension, valor)
        self._clientes_ambiguos = []
        por_id, por_nombre = self._indice_clientes(meta)
        ids = [(m.start(), m.end(), "cliente", por_id[m.group(0)]) for m in re.finditer(r"\bc\d{5}\b", t) if m.group(0) in por_id]
        candidatos += ids
        if not ids:
            for nombre, vals in por_nombre.items():
                for m in re.finditer(rf"\b{re.escape(nombre)}\b", t):
                    if len(vals) == 1:
                        candidatos.append((m.start(), m.end(), "cliente", vals[0]))
                    elif (nombre, vals) not in self._clientes_ambiguos:
                        self._clientes_ambiguos.append((nombre, vals))
        for dim in PRIORIDAD_DIM:
            if dim == "cliente":
                continue
            for v in meta.valores.get(dim, []):
                nv = normalizar(v)
                if len(nv) < 3:
                    continue
                for m in re.finditer(rf"\b{re.escape(nv)}\b", t):
                    candidatos.append((m.start(), m.end(), dim, v))
        for alias, (dim, v) in ALIAS_VALORES.items():
            for m in re.finditer(rf"\b{re.escape(alias)}\b", t):
                candidatos.append((m.start(), m.end(), dim, v))
        # Prioriza coincidencias más largas, luego la prioridad de dimensión
        candidatos.sort(key=lambda c: (-(c[1] - c[0]), PRIORIDAD_DIM.index(c[2]) if c[2] in PRIORIDAD_DIM else 99))
        ocupado = [False] * len(t)
        elegidos = []
        for ini, fin, dim, v in candidatos:
            if any(ocupado[ini:fin]):
                continue
            # "segmento corporativo" vs "tipo de canal corporativo": el contexto decide
            if v == "Corporativo" and dim == "tipo_canal" and "canal" not in t:
                continue
            for k in range(ini, fin):
                ocupado[k] = True
            elegidos.append((ini, dim, v))
        elegidos.sort()
        filtros: dict[str, list] = {}
        for _, dim, v in elegidos:
            if v not in filtros.setdefault(dim, []):
                filtros[dim].append(v)
        t2 = "".join(" " if ocupado[i] else ch for i, ch in enumerate(t))
        return [{"dimension": d, "valores": vs} for d, vs in filtros.items()], " ".join(t2.split())

    # ---------------------------------------------------------------------------------------------
    def _periodos(self, t: str, meta) -> tuple[list[dict], str]:
        encontrados = []    # (posición, dict)

        def consumir(m):
            nonlocal t
            t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]

        def num(s):
            return NUMEROS.get(s, None) if not s.isdigit() else int(s)

        hoy = date.today()
        A = r"(?: (?:de |del )?(?:ano )?(20\d\d))?"          # año opcional: "T1 2026", "T1 de 2026", "del año 2026"
        MES_RE = "|".join(MESES)

        def rango_meses(m):
            m1, m2 = MESES[m.group(1)], MESES[m.group(3)]
            y2 = int(m.group(4)) if m.group(4) else (int(m.group(2)) if m.group(2) else None)
            y1 = int(m.group(2)) if m.group(2) else y2
            sup = None
            if not y2:     # sin año: el más reciente con datos para todo el rango
                y2 = meta.fecha_max.year if m2 <= meta.fecha_max.month else meta.fecha_max.year - 1
                y1 = y2 if m1 <= m2 else y2 - 1
                sup = f"No se indicó el año: se asumió {MESES_NOMBRE[m1]}–{MESES_NOMBRE[m2]} {y2} (el más reciente con datos)."
            return {"tipo": "rango", "desde": f"{y1}-{m1:02d}", "hasta": f"{y2}-{m2:02d}", "supuesto": sup}

        def relativo(desde, hasta, etiqueta):
            return {"tipo": "rango", "desde": desde.isoformat(), "hasta": hasta.isoformat(), "etiqueta": etiqueta}

        lunes = hoy - timedelta(days=hoy.weekday())
        primero_mes = hoy.replace(day=1)
        fin_mes_pasado = primero_mes - timedelta(days=1)
        patrones = [
            (r"\bayer\b", lambda m: relativo(hoy - timedelta(days=1), hoy - timedelta(days=1), "ayer")),
            (r"\bhoy\b", lambda m: relativo(hoy, hoy, "hoy")),
            (r"\b(?:la )?semana pasada\b|\bsemana anterior\b",
             lambda m: relativo(lunes - timedelta(days=7), lunes - timedelta(days=1), "la semana pasada")),
            (r"\besta semana\b", lambda m: relativo(lunes, hoy, "esta semana")),
            (r"\b(?:el )?mes pasado\b|\bmes anterior\b",
             lambda m: relativo(fin_mes_pasado.replace(day=1), fin_mes_pasado, "el mes pasado")),
            (r"\beste mes\b|\bmes en curso\b", lambda m: relativo(primero_mes, hoy, "este mes")),
            (rf"\b(?:en )?(?:los |las )?ultim[oa]s {NUM} mes(?:es)?(?: disponibles?)?\b",
             lambda m: {"tipo": "ultimos_meses", "n": num(m.group(1))}),
            (rf"\b(?:en )?(?:los |las )?ultim[oa]s {NUM} trimestres?(?: disponibles?)?\b",
             lambda m: {"tipo": "ultimos_meses", "n": 3 * num(m.group(1))}),
            (rf"\b(?:en )?(?:los |las )?ultim[oa]s {NUM} semestres?(?: disponibles?)?\b",
             lambda m: {"tipo": "ultimos_meses", "n": 6 * num(m.group(1))}),
            (rf"\b(?:en )?(?:los |las )?ultim[oa]s {NUM} anos?(?: disponibles?)?\b",
             lambda m: {"tipo": "ultimos_meses", "n": 12 * num(m.group(1))}),
            (r"\bultimo mes(?: disponible)?\b", lambda m: {"tipo": "ultimos_meses", "n": 1}),
            (r"\bultimo trimestre(?: disponible)?\b",
             lambda m: {"tipo": "trimestre", "anio": meta.fecha_max.year, "numero": (meta.fecha_max.month - 1) // 3 + 1}),
            (r"\bultimo semestre(?: disponible)?\b", lambda m: {"tipo": "ultimos_meses", "n": 6}),
            (r"\bultimo ano(?: disponible)?\b|\bultimos 12 meses\b", lambda m: {"tipo": "ultimos_meses", "n": 12}),
            (r"\b(?:en )?lo que va (?:del|de) ano(?: (20\d\d))?\b|\bytd\b|\bano a la fecha\b",
             lambda m: {"tipo": "ytd", "anio": int(m.group(1)) if m.lastindex and m.group(1) else None}),
            (r"\b(primer|primero|1er|segundo|2do|tercer|tercero|3er|cuarto|4to|[1-4])(?: |o |er |do |ro |to )?trimestre" + A + r"\b",
             lambda m: {"tipo": "trimestre", "numero": ORDINALES[m.group(1)], "anio": int(m.group(2)) if m.group(2) else None}),
            (r"\bt([1-4])(?: |-)?(?:(?:de|del) )?(20\d\d)?\b",
             lambda m: {"tipo": "trimestre", "numero": int(m.group(1)), "anio": int(m.group(2)) if m.group(2) else None}),
            (r"\b(primer|1er|segundo|2do)(?: )?semestre" + A + r"\b",
             lambda m: {"tipo": "semestre", "numero": 1 if m.group(1) in ("primer", "1er") else 2,
                        "anio": int(m.group(2)) if m.group(2) else None}),
            (r"\b(?:desde |de )?(" + MES_RE + r")" + A + r" (?:a|al|hasta) (" + MES_RE + r")" + A + r"\b", rango_meses),
            (r"\bentre (" + MES_RE + r")" + A + r" y (" + MES_RE + r")" + A + r"\b", rango_meses),
            (r"\b(" + MES_RE + r")" + A + r"\b",
             lambda m: {"tipo": "mes", "numero": MESES[m.group(1)], "anio": int(m.group(2)) if m.group(2) else None}),
            (r"\beste ano\b|\bano actual\b|\bano en curso\b", lambda m: {"tipo": "anio", "anio": meta.fecha_max.year}),
            (r"\bano pasado\b|\bano anterior\b", lambda m: {"tipo": "anio", "anio": meta.fecha_max.year - 1}),
            (r"\b(?:del |en |el |ano |durante )?(20\d\d)\b", lambda m: {"tipo": "anio", "anio": int(m.group(1))}),
        ]
        for patron, fabrica in patrones:
            while True:
                m = re.search(patron, t)
                if not m:
                    break
                encontrados.append((m.start(), fabrica(m)))
                consumir(m)
        encontrados.sort(key=lambda x: x[0])
        periodos = [p for _, p in encontrados]
        # completa el año faltante con el de otro periodo mencionado ("enero vs febrero de 2026")
        anios = [p.get("anio") for p in periodos if p.get("anio")]
        if anios and len(periodos) >= 2:
            for p in periodos:
                if p.get("tipo") in ("mes", "trimestre", "semestre") and not p.get("anio"):
                    p["anio"] = anios[-1]
        return periodos, " ".join(t.split())

    # ---------------------------------------------------------------------------------------------
    @staticmethod
    def _dimension_inexistente(t: str) -> str | None:
        for clave in sorted(DIMENSIONES_NO_DISPONIBLES, key=len, reverse=True):
            if re.search(rf"\b(por|cada|que|cual|cuales|segun|del?|el|los|las|mejor|peor)\s+(el |la |los |las )?{re.escape(clave)}\b", t):
                return DIMENSIONES_NO_DISPONIBLES[clave]
        m = re.search(r"\bpor (?:el |la |los |las |cada )?([a-z]{4,})\b", t)
        if m and m.group(1) not in STOP_POR:
            palabra = m.group(1)
            conocidas = [p for p, _ in DIMENSIONES_PATRONES]
            if not any(re.search(p, f"por {palabra}") for p in conocidas) and \
                    not any(re.search(rf"\b(?:{p})\b", palabra) for p, _ in METRICAS_PATRONES):
                return palabra
        return None

    @staticmethod
    def _dimension(t: str, filtros: list[dict]) -> str | None:
        """Elige la dimensión de agrupación; ignora menciones que sólo dan contexto a un filtro."""
        menciones = []
        for patron, codigo in DIMENSIONES_PATRONES:
            for m in re.finditer(patron, t):
                menciones.append((m.start(), m.end(), codigo))
        menciones.sort()
        dims_filtradas = {f["dimension"] for f in filtros}
        for ini, fin, cod in menciones:
            previa_pal = (t[:ini].split()[-1:] or [""])[0]
            if cod == "cliente" and dims_filtradas & {"segmento", "tipo_cliente"} and \
                    previa_pal not in ("por", "cada", "que", "cual", "cuales", "top") and not re.match(r"\d+$", previa_pal) \
                    and previa_pal not in NUMEROS:
                continue     # "los clientes premium": contexto del filtro de segmento, no agrupación por cliente
            if cod in dims_filtradas:
                # "la categoría Bebidas", "del canal app": la mención sólo da contexto al filtro, salvo que
                # sea plural o vaya precedida de un agrupador ("por canal", "qué canal", "cada canal").
                previa = t[:ini].split()[-1:] or [""]
                plural = t[ini:fin].endswith("s")
                agrupador = previa[0] in ("por", "cada", "que", "cual", "cuales", "segun", "entre")
                if not plural and not agrupador:
                    continue
            return cod
        return None

    @staticmethod
    def _limite(t: str, dimension: str | None, operacion: str, completo: str = "") -> int | None:
        if operacion not in ("ranking",) or not dimension:
            return None
        m = re.search(rf"\b(?:top|los|las|primer[oa]s|mejores|peores|principales)?\s*{NUM}\s+(?:\w+\s+)?"
                      rf"(categorias|subcategorias|productos|articulos|clientes|sucursales|canales|marcas|segmentos|meses|"
                      rf"ciudades|regiones|estados|trimestres|items)\b", t)
        if m:
            n = m.group(1)
            return int(n) if n.isdigit() else NUMEROS.get(n)
        m = re.search(r"\btop\s*(\d+)\b", t)
        if m:
            return int(m.group(1))
        palabras = {"categoria": "categoria", "subcategoria": "subcategoria", "producto": "producto|articulo",
                    "marca": "marca", "cliente": "cliente", "segmento": "segmento", "tipo_cliente": "tipocliente",
                    "sucursal": "sucursal|sede|tienda", "ciudad": "ciudad", "estado": "estado", "region": "region|zona",
                    "canal": "canal", "tipo_canal": "tipocanal", "mes": "mes", "trimestre": "trimestre", "anio": "ano",
                    "semestre": "semestre", "dia_semana": "diasemana", "ciudad_cliente": "ciudad"}.get(dimension, dimension)
        completo = completo or t
        singular = re.search(rf"\b(que|cual|el|la)\s+(?:mejor|peor|mayor|menor|principal|primer)?\s*({palabras})\b(?!es\b|s\b)", completo)
        if singular and (re.search(MAYOR, completo) or re.search(MENOR, completo) or re.search(r"\bmas vendid|\blider", completo)):
            return 1
        if re.search(rf"(^|\b(la|el)\s+)({palabras})\s+(con|de)\s+(mayor|menor|mas|menos|mejor|peor)\b", completo.strip()):
            return 1
        return None
