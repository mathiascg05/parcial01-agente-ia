"""
Intérpretes de lenguaje natural (patrón Strategy).

Todos los intérpretes producen el MISMO diccionario estructurado (esquema común) y una sola función,
construir_intencion(), lo convierte en un objeto Intencion validado. Así el LLM nunca decide SQL:
sólo propone códigos del catálogo, que luego son verificados por las reglas de validación.

Esquema común:
{
  "tipo": "consulta|ambigua|fuera_de_alcance|dimension_inexistente|operacion_no_autorizada|faltan_parametros",
  "operacion": "total|ranking|tendencia|comparacion_periodos|comparacion_miembros",
  "metrica": "<código de METRICAS>|null",
  "dimension": "<código de DIMENSIONES>|null",
  "dimension_texto": "<texto de una dimensión no disponible>|null",
  "periodo": {"tipo": "todo|anio|semestre|trimestre|mes|rango|ultimos_meses|ytd", "anio": int, "numero": int,
              "desde": "AAAA-MM[-DD]", "hasta": "AAAA-MM[-DD]", "n": int} | null,
  "periodo_comparacion": {...} | null,
  "filtros": [{"dimension": "<código>", "valores": ["..."]}],
  "orden": "asc|desc", "limite": int|null, "desglose": "mes|trimestre|null",
  "opciones": [...], "faltantes": [...], "motivo": "...", "supuestos": [...]
}
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import date

from agente.bdoo.modelo import Intencion
from agente.bdoo.tda import ErrorTDA, Filtro, Periodo, _fin_de_mes, etiqueta_mes
from agente.catalogo import DIMENSIONES, METRICAS


class ErrorInterpretacion(RuntimeError):
    pass


class InterpreteBase(ABC):
    nombre = "base"

    @abstractmethod
    def interpretar(self, texto: str, meta, contexto: dict | None = None) -> dict:
        """Devuelve el diccionario del esquema común."""


# ---------------------------------------------------------------------------------------------
def _parse_fecha(valor: str, fin: bool) -> date:
    valor = str(valor).strip()
    if re.fullmatch(r"\d{4}-\d{2}", valor):
        d = date(int(valor[:4]), int(valor[5:7]), 1)
        return _fin_de_mes(d) if fin else d
    if re.fullmatch(r"\d{4}", valor):
        return date(int(valor), 12, 31) if fin else date(int(valor), 1, 1)
    return date.fromisoformat(valor[:10])


def resolver_periodo(p: dict | None, meta, supuestos: list) -> Periodo:
    """Convierte la especificación de periodo en un TDA Periodo usando el rango del Data Mart."""
    fmin, fmax = meta.fecha_min, meta.fecha_max
    if not p or p.get("tipo") in (None, "todo", "ninguno"):
        return Periodo(fmin, fmax, f"todo el rango disponible ({etiqueta_mes(fmin)} a {etiqueta_mes(fmax)})",
                       explicito=False)
    tipo = p.get("tipo")
    anio = p.get("anio")
    numero = p.get("numero")
    try:
        if tipo == "anio":
            return Periodo.del_anio(int(anio or fmax.year))
        if tipo == "ytd":
            a = int(anio or fmax.year)
            hasta = min(fmax, date(a, 12, 31)) if a == fmax.year else date(a, fmax.month, _fin_de_mes(date(a, fmax.month, 1)).day)
            return Periodo(date(a, 1, 1), hasta, f"ene a {etiqueta_mes(hasta)}")
        if tipo == "semestre":
            if not anio:
                anio = fmax.year if Periodo.del_semestre(fmax.year, int(numero)).desde <= fmax else fmax.year - 1
                supuestos.append(f"No se indicó el año del semestre: se asumió {anio} (el más reciente con datos).")
            return Periodo.del_semestre(int(anio), int(numero))
        if tipo == "trimestre":
            if not anio:
                anio = fmax.year if Periodo.del_trimestre(fmax.year, int(numero)).desde <= fmax else fmax.year - 1
                supuestos.append(f"No se indicó el año del trimestre: se asumió T{numero}-{anio} (el más reciente con datos).")
            return Periodo.del_trimestre(int(anio), int(numero))
        if tipo == "mes":
            if not anio:
                anio = fmax.year if date(fmax.year, int(numero), 1) <= fmax else fmax.year - 1
                supuestos.append(f"No se indicó el año del mes: se asumió {anio} (el más reciente con datos).")
            return Periodo.del_mes(int(anio), int(numero))
        if tipo == "ultimos_meses":
            n = int(p.get("n") or 3)
            return Periodo.ultimos_meses(n, fmax)
        if tipo == "rango":
            if p.get("supuesto"):
                supuestos.append(p["supuesto"])
            return Periodo(_parse_fecha(p["desde"], False), _parse_fecha(p["hasta"], True), p.get("etiqueta") or "")
    except (ErrorTDA, KeyError, ValueError, TypeError) as e:
        raise ErrorInterpretacion(f"Periodo inválido {p}: {e}") from e
    raise ErrorInterpretacion(f"Tipo de periodo desconocido: {tipo}")


def nombre_intencion(datos: dict) -> str:
    if datos.get("operacion") in ("comparacion_periodos", "comparacion_miembros"):
        return "comparar_desempeno"
    met = METRICAS.get(datos.get("metrica") or "")
    if met and met.intencion == "analizar_rentabilidad":
        return "analizar_rentabilidad"
    dim = DIMENSIONES.get(datos.get("dimension") or "")
    if dim:
        return dim.intencion
    return met.intencion if met else "analizar_ventas"


def intencion_a_datos(i: Intencion) -> dict:
    """Inverso aproximado: usado para preguntas de seguimiento ('¿y en 2025?')."""
    def per(p):
        return {"tipo": "rango", "desde": p.desde.isoformat(), "hasta": p.hasta.isoformat(), "etiqueta": p.etiqueta} if p else None
    return {"tipo": "consulta", "operacion": i.operacion, "metrica": i.metrica, "dimension": i.dimension,
            "periodo": per(i.periodo) if i.periodo and i.periodo.explicito else None,
            "periodo_comparacion": per(i.periodo_comparacion),
            "filtros": [f.a_dict() for f in i.filtros], "orden": i.orden, "limite": i.limite, "desglose": i.desglose}


def construir_intencion(datos: dict, meta, origen: str) -> Intencion:
    """Normaliza y valida el diccionario del intérprete y crea el objeto Intencion."""
    supuestos = list(datos.get("supuestos") or [])
    tipo = datos.get("tipo") or "consulta"
    if tipo not in Intencion.TIPOS:
        tipo = "fuera_de_alcance"
    if tipo != "consulta":
        return Intencion(tipo, origen=origen, dimension_texto=datos.get("dimension_texto"),
                         opciones=datos.get("opciones"), faltantes=datos.get("faltantes"),
                         motivo=datos.get("motivo", ""), datos_crudos=datos, supuestos=supuestos,
                         metrica=datos.get("metrica") if datos.get("metrica") in METRICAS else None,
                         dimension=datos.get("dimension") if datos.get("dimension") in DIMENSIONES else None)

    metrica = datos.get("metrica")
    dimension = datos.get("dimension") or None
    if metrica not in METRICAS:
        return Intencion("ambigua", origen=origen, motivo="No se identificó una métrica válida del catálogo.",
                         opciones=["ingreso_neto", "margen_bruto", "unidades", "ticket_promedio"], datos_crudos=datos)
    if dimension and dimension not in DIMENSIONES:
        return Intencion("dimension_inexistente", origen=origen, dimension_texto=str(dimension),
                         motivo=f"La dimensión '{dimension}' no existe en el Data Mart.", datos_crudos=datos)

    filtros = []
    for f in datos.get("filtros") or []:
        dim = f.get("dimension")
        if dim not in DIMENSIONES:
            return Intencion("dimension_inexistente", origen=origen, dimension_texto=str(dim),
                             motivo=f"La dimensión de filtro '{dim}' no existe en el Data Mart.", datos_crudos=datos)
        valores = []
        for v in f.get("valores") or []:
            canon = meta.resolver_valor(dim, v)
            valores.append(canon or v)       # si no existe, RV05 lo detecta y sugiere alternativas
        if valores:
            filtros.append(Filtro(dim, tuple(valores)))

    operacion = datos.get("operacion")
    if operacion not in ("total", "ranking", "tendencia", "comparacion_periodos", "comparacion_miembros"):
        operacion = "ranking" if dimension else "total"
    if operacion in ("ranking", "tendencia", "comparacion_miembros") and not dimension:
        operacion = "total"
    if operacion == "tendencia" and dimension and not DIMENSIONES[dimension].temporal:
        operacion = "ranking"
    if operacion == "total" and dimension:
        # "Ventas por canal" pedida como total: un total no se agrupa; con dimensión es un desglose.
        operacion = "tendencia" if DIMENSIONES[dimension].temporal else "ranking"

    periodo = resolver_periodo(datos.get("periodo"), meta, supuestos)
    periodo_comp = None
    if operacion == "comparacion_periodos":
        if datos.get("periodo_comparacion"):
            periodo_comp = resolver_periodo(datos["periodo_comparacion"], meta, supuestos)
        else:
            if not periodo.explicito:
                a = meta.fecha_max.year
                periodo = Periodo(date(a, 1, 1), meta.fecha_max, f"ene a {etiqueta_mes(meta.fecha_max)}")
                supuestos.append(f"No se indicaron periodos: se comparó {periodo} contra el mismo periodo del año anterior.")
            else:
                supuestos.append("No se indicó periodo base: se comparó contra el mismo periodo del año anterior.")
            periodo_comp = periodo.mismo_periodo_anio_anterior()
        if periodo_comp.desde > periodo.desde:           # el periodo "actual" es el más reciente
            periodo, periodo_comp = periodo_comp, periodo
        # Periodos comparables: si el actual está cubierto sólo en parte (p. ej. 2026 llega a sep), se recorta
        # y el periodo base se recorta a los mismos meses del año correspondiente (ene–sep vs ene–sep).
        fmax = meta.fecha_max
        if periodo.desde <= fmax < periodo.hasta and abs(periodo.dias - periodo_comp.dias) <= 3:
            dy = periodo.desde.year - periodo_comp.desde.year
            try:
                hasta_base = fmax.replace(year=fmax.year - dy)
            except ValueError:
                hasta_base = fmax.replace(year=fmax.year - dy, day=28)
            et_a = f"{etiqueta_mes(periodo.desde)} a {etiqueta_mes(fmax)}"
            et_b = f"{etiqueta_mes(periodo_comp.desde)} a {etiqueta_mes(hasta_base)}"
            supuestos.append(f"{periodo} sólo tiene datos hasta {etiqueta_mes(fmax)}: para comparar periodos equivalentes "
                             f"se usó {et_a} contra {et_b}.")
            periodo = Periodo(periodo.desde, fmax, et_a)
            periodo_comp = Periodo(periodo_comp.desde, hasta_base, et_b)

    if periodo_comp is not None:
        if periodo.se_solapa(periodo_comp):
            supuestos.append(f"Atención: {periodo} y {periodo_comp} se solapan (uno contiene al otro); la variación no es "
                             f"una comparación entre periodos independientes.")
        elif abs(periodo.dias - periodo_comp.dias) > 3:
            supuestos.append(f"Atención: los periodos comparados tienen distinta duración ({periodo.dias} vs "
                             f"{periodo_comp.dias} días); la variación refleja también esa diferencia.")

    limite = datos.get("limite")
    try:
        limite = int(limite) if limite not in (None, "", 0) else None
    except (TypeError, ValueError):
        limite = None
    if limite is not None and not 1 <= limite <= 100:
        limite = min(max(limite, 1), 100)
    if operacion == "ranking" and dimension in ("producto", "cliente") and not limite:
        limite = 10
        supuestos.append("Se muestran los 10 primeros resultados.")

    desglose = datos.get("desglose")
    if desglose not in DIMENSIONES or not DIMENSIONES[desglose].temporal or operacion != "comparacion_miembros":
        desglose = None

    datos = {**datos, "operacion": operacion}
    return Intencion("consulta", nombre=nombre_intencion(datos), operacion=operacion, metrica=metrica,
                     dimension=dimension, periodo=periodo, periodo_comparacion=periodo_comp, filtros=filtros,
                     orden=datos.get("orden") or "desc", limite=limite, desglose=desglose, origen=origen,
                     datos_crudos=datos, supuestos=supuestos)
