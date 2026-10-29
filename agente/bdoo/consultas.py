"""
Catálogo de consultas analíticas parametrizadas (ConsultaAnalitica y subclases).

Patrón Template Method: ConsultaAnalitica.ejecutar() define el algoritmo fijo (construir SQL ->
ejecutar en el Data Mart -> empaquetar ResultadoConsulta) y cada subclase implementa el paso
variable construir_sql() (polimorfismo). aplica_a() permite seleccionar la consulta adecuada para
una intención (patrón Strategy / selección polimórfica).

Seguridad: los identificadores SQL provienen sólo de agente/catalogo.py (listas blancas) y los
valores viajan como parámetros con nombre (%(p_desde)s ...). Nunca se concatena texto del usuario.
"""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from persistent.list import PersistentList

from agente.bdoo.modelo import ObjetoAgente, ResultadoConsulta, _ref
from agente.catalogo import DIMENSIONES, JOINS, METRICAS

ORDEN_JOINS = ["f", "p", "c", "s", "n"]

# Métricas que se muestran como contexto junto a la métrica principal
CONTEXTO_METRICA = {
    "margen_bruto": ["margen_pct"],
    "margen_pct": ["margen_bruto", "ingreso_neto"],
    "ticket_promedio": ["transacciones"],
    "descuento_pct": ["descuento"],
    "descuento": ["descuento_pct"],
    "costo": ["ingreso_neto"],
}


def especial(col: str) -> str:
    """Expresión booleana: el miembro es especial (No informado / Sin correspondencia). Se ordena al final
    para que nunca 'gane' un ranking, pero se sigue mostrando (no se pierden ingresos)."""
    return (f"({col}::TEXT ILIKE '%%sin correspondencia%%' OR {col}::TEXT ILIKE '%%no informad%%' "
            f"OR {col}::TEXT ILIKE '%%consumidor final%%')")


class ConsultaAnalitica(ObjetoAgente):
    """Encapsula una plantilla SQL, sus parámetros, sus fuentes y su versión."""

    operacion = ""

    def __init__(self, codigo: str, nombre: str, descripcion: str, plantilla: str, fuentes: list):
        if type(self) is ConsultaAnalitica:
            raise TypeError("ConsultaAnalitica es abstracta")
        super().__init__()
        self._codigo = codigo
        self._nombre = nombre
        self._descripcion = descripcion
        self._plantilla = plantilla
        self._fuentes = PersistentList(fuentes)
        self._version = 1
        self._historial_versiones = PersistentList([(1, datetime.now().isoformat(timespec="seconds"),
                                                     "Versión inicial", plantilla)])
        self._ejecuciones = 0

    codigo = property(lambda s: s._codigo)
    nombre = property(lambda s: s._nombre)
    descripcion = property(lambda s: s._descripcion)
    plantilla = property(lambda s: s._plantilla)
    version = property(lambda s: s._version)
    fuentes = property(lambda s: list(s._fuentes))
    ejecuciones = property(lambda s: s._ejecuciones)
    historial_versiones = property(lambda s: [tuple(v) for v in s._historial_versiones])

    # -- versionamiento explícito --------------------------------------------------------------
    def nueva_version(self, nota: str, plantilla: str | None = None) -> int:
        self._version += 1
        if plantilla:
            self._plantilla = plantilla
        self._historial_versiones.append((self._version, datetime.now().isoformat(timespec="seconds"), nota,
                                          self._plantilla))
        return self._version

    # -- comportamiento polimórfico -------------------------------------------------------------
    @abstractmethod
    def aplica_a(self, intencion) -> bool:
        raise NotImplementedError

    @abstractmethod
    def construir_sql(self, intencion) -> tuple[str, dict]:
        raise NotImplementedError

    def ejecutar(self, datamart, intencion, sql: str | None = None, params: dict | None = None) -> ResultadoConsulta:
        """Template Method: construir -> ejecutar -> empaquetar."""
        from agente.datamart import ErrorDataMart
        if sql is None:
            sql, params = self.construir_sql(intencion)
        self._ejecuciones += 1
        try:
            columnas, filas, ms = datamart.ejecutar(sql, params)
            return ResultadoConsulta(self, sql, params, columnas, filas, ms)
        except ErrorDataMart as e:
            return ResultadoConsulta(self, sql, params, [], [], 0, error=str(e))

    # -- utilidades comunes para las subclases ---------------------------------------------------
    @staticmethod
    def _metricas_contexto(intencion) -> list[str]:
        return [m for m in CONTEXTO_METRICA.get(intencion.metrica, []) if m != intencion.metrica]

    @staticmethod
    def _aliases(intencion, extra_dims=()) -> list[str]:
        alias = {"f"}
        for m in [intencion.metrica, *ConsultaAnalitica._metricas_contexto(intencion)]:
            alias.update(METRICAS[m].alias_requeridos)
        for d in [intencion.dimension, intencion.desglose, *extra_dims]:
            if d:
                alias.add(DIMENSIONES[d].alias)
        for f in intencion.filtros:
            alias.add(DIMENSIONES[f.dimension].alias)
        return [a for a in ORDEN_JOINS if a in alias]

    @staticmethod
    def _from(aliases) -> str:
        return "FROM dm.fact_ventas v\n" + "\n".join(JOINS[a] for a in aliases)

    @staticmethod
    def _where(intencion, params: dict, periodo=None, prefijo: str = "p") -> str:
        periodo = periodo or intencion.periodo
        params[f"{prefijo}_desde"] = periodo.desde
        params[f"{prefijo}_hasta"] = periodo.hasta
        condiciones = [f"f.fecha BETWEEN %({prefijo}_desde)s AND %({prefijo}_hasta)s"]
        for i, filtro in enumerate(intencion.filtros):
            nombre = f"f{i}"
            params[nombre] = list(filtro.valores)
            condiciones.append(f"{DIMENSIONES[filtro.dimension].expresion} = ANY(%({nombre})s)")
        return "WHERE " + "\n  AND ".join(condiciones)

    @staticmethod
    def _select_metricas(intencion) -> list[str]:
        cols = [f"{METRICAS[intencion.metrica].expresion} AS {intencion.metrica}"]
        cols += [f"{METRICAS[m].expresion} AS {m}" for m in ConsultaAnalitica._metricas_contexto(intencion)]
        return cols

    def describir(self) -> str:
        return f"{self._codigo} v{self._version} — {self._nombre}"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "codigo": self._codigo, "nombre": self._nombre, "operacion": self.operacion,
                "descripcion": self._descripcion, "plantilla": self._plantilla, "version": self._version,
                "historial_versiones": [list(v[:3]) for v in self._historial_versiones],
                "fuentes_ido": [_ref(f) for f in self._fuentes], "ejecuciones": self._ejecuciones}


# =============================================================================================
class ConsultaTotal(ConsultaAnalitica):
    """Agregado de una métrica para un periodo y filtros (sin dimensión de agrupación)."""
    operacion = "total"

    def aplica_a(self, intencion) -> bool:
        return intencion.dimension is None and intencion.periodo_comparacion is None

    def construir_sql(self, intencion):
        params: dict = {}
        cols = self._select_metricas(intencion) + ["COUNT(*) AS lineas"]
        sql = (f"SELECT {', '.join(cols)}\n{self._from(self._aliases(intencion))}\n{self._where(intencion, params)}\n"
               f"HAVING COUNT(*) > 0")
        return sql, params


class ConsultaRanking(ConsultaAnalitica):
    """Métrica agrupada por una dimensión, ordenada (ranking / top N)."""
    operacion = "ranking"

    def aplica_a(self, intencion) -> bool:
        if intencion.dimension is None or intencion.periodo_comparacion is not None:
            return False
        if intencion.operacion == "comparacion_miembros":
            return False
        return not (DIMENSIONES[intencion.dimension].temporal and intencion.operacion == "tendencia")

    def construir_sql(self, intencion):
        params: dict = {}
        dim = DIMENSIONES[intencion.dimension]
        m = METRICAS[intencion.metrica]
        cols = [f"{dim.expresion} AS {dim.codigo}"] + self._select_metricas(intencion)
        if m.aditividad == "aditiva":
            cols.append(f"ROUND(100.0 * {m.expresion} / NULLIF(SUM({m.expresion}) OVER (), 0), 2) AS participacion_pct")
        group = dim.expresion if not dim.orden_columna or dim.orden_columna == dim.columna \
            else f"{dim.expresion}, {dim.alias}.{dim.orden_columna}"
        orden = "ASC" if intencion.orden == "asc" else "DESC"
        sql = (f"SELECT {', '.join(cols)}\n{self._from(self._aliases(intencion))}\n{self._where(intencion, params)}\n"
               f"GROUP BY {group}\n"
               + (f"HAVING {m.expresion} > 0\n" if intencion.metrica == "clientes_activos" else "")
               + f"ORDER BY {especial(dim.expresion)}, {intencion.metrica} {orden} NULLS LAST, {dim.codigo}")
        if intencion.limite:
            params["limite"] = int(intencion.limite)
            sql += "\nLIMIT %(limite)s"
        return sql, params


class ConsultaTendencia(ConsultaAnalitica):
    """Serie temporal ordenada cronológicamente con variación respecto al periodo anterior."""
    operacion = "tendencia"

    def aplica_a(self, intencion) -> bool:
        return (intencion.dimension is not None and DIMENSIONES[intencion.dimension].temporal
                and intencion.operacion == "tendencia" and intencion.periodo_comparacion is None)

    def construir_sql(self, intencion):
        params: dict = {}
        dim = DIMENSIONES[intencion.dimension]
        m = METRICAS[intencion.metrica]
        cols = [f"{dim.expresion} AS {dim.codigo}"] + self._select_metricas(intencion)
        cols.append(f"ROUND((({m.expresion})::NUMERIC / NULLIF(LAG({m.expresion}) OVER (ORDER BY {dim.expresion}), 0) - 1) * 100, 2)"
                    f" AS variacion_pct")
        sql = (f"SELECT {', '.join(cols)}\n{self._from(self._aliases(intencion))}\n{self._where(intencion, params)}\n"
               f"GROUP BY {dim.expresion}\nORDER BY {dim.expresion}")
        return sql, params


class ConsultaComparativaPeriodos(ConsultaAnalitica):
    """Compara una métrica entre un periodo actual y un periodo base (opcionalmente por dimensión)."""
    operacion = "comparacion_periodos"

    def aplica_a(self, intencion) -> bool:
        return intencion.periodo_comparacion is not None

    def construir_sql(self, intencion):
        params: dict = {}
        m = METRICAS[intencion.metrica]
        aliases = self._from(self._aliases(intencion))
        if intencion.dimension:
            dim = DIMENSIONES[intencion.dimension]
            sel, grp, clave = f"{dim.expresion} AS {dim.codigo}, ", f"\nGROUP BY {dim.expresion}", dim.codigo
        else:
            sel, grp, clave = "'Total'::TEXT AS total, ", "", "total"
        where_a = self._where(intencion, params, intencion.periodo, "a")
        where_b = self._where(intencion, params, intencion.periodo_comparacion, "b")
        orden = "ASC" if intencion.orden == "asc" else "DESC"
        sql = (f"WITH actual AS (\n  SELECT {sel}{m.expresion} AS valor\n  {aliases}\n  {where_a}{grp}\n),\n"
               f"base AS (\n  SELECT {sel}{m.expresion} AS valor\n  {aliases}\n  {where_b}{grp}\n)\n"
               f"SELECT {clave}, b.valor AS valor_base, a.valor AS valor_actual,\n"
               f"       a.valor - b.valor AS variacion,\n"
               f"       ROUND((a.valor::NUMERIC / NULLIF(b.valor, 0) - 1) * 100, 2) AS variacion_pct\n"
               f"FROM actual a FULL JOIN base b USING ({clave})\n"
               f"ORDER BY {especial(clave)}, variacion {orden} NULLS LAST, {clave}")
        if intencion.limite:
            params["limite"] = int(intencion.limite)
            sql += "\nLIMIT %(limite)s"
        return sql, params


class ConsultaComparativaMiembros(ConsultaAnalitica):
    """Compara dos o más miembros de una dimensión (p. ej. dos canales), con desglose temporal opcional.
    Usa GROUPING SETS para que el total del periodo se RECALCULE (correcto para métricas no aditivas)."""
    operacion = "comparacion_miembros"

    def aplica_a(self, intencion) -> bool:
        return intencion.operacion == "comparacion_miembros" and intencion.dimension is not None \
            and intencion.periodo_comparacion is None

    def construir_sql(self, intencion):
        params: dict = {}
        dim = DIMENSIONES[intencion.dimension]
        cols = [f"{dim.expresion} AS {dim.codigo}"]
        if intencion.desglose:
            des = DIMENSIONES[intencion.desglose]
            cols.append(f"COALESCE({des.expresion}::TEXT, 'Total periodo') AS {des.codigo}")
            grupos = f"GROUP BY GROUPING SETS (({dim.expresion}, {des.expresion}), ({dim.expresion}))"
            orden = f"ORDER BY {dim.codigo}, GROUPING({des.expresion}), {des.expresion}"
        else:
            grupos, orden = f"GROUP BY {dim.expresion}", f"ORDER BY {intencion.metrica} DESC"
        cols += self._select_metricas(intencion)
        sql = (f"SELECT {', '.join(cols)}\n{self._from(self._aliases(intencion))}\n{self._where(intencion, params)}\n"
               f"{grupos}\n{orden}")
        return sql, params


def crear_catalogo(fuentes: dict) -> list[ConsultaAnalitica]:
    """Fábrica del catálogo (orden = prioridad de selección)."""
    todas = list(fuentes.values())
    return [
        ConsultaComparativaPeriodos("CQ-04", "Comparación entre periodos",
                                    "Variación de una métrica entre periodo actual y periodo base, por dimensión",
                                    "WITH actual AS (...), base AS (...) SELECT dim, base, actual, variación", todas),
        ConsultaComparativaMiembros("CQ-05", "Comparación entre miembros",
                                    "Métrica para 2+ miembros de una dimensión con desglose temporal opcional",
                                    "SELECT dim, [mes], métrica ... GROUP BY GROUPING SETS", todas),
        ConsultaTendencia("CQ-03", "Tendencia temporal",
                          "Serie cronológica de una métrica con variación % respecto al periodo anterior",
                          "SELECT tiempo, métrica, LAG(...) ... GROUP BY tiempo ORDER BY tiempo", todas),
        ConsultaRanking("CQ-02", "Ranking por dimensión",
                        "Métrica agrupada por dimensión, ordenada asc/desc, con límite y participación %",
                        "SELECT dim, métrica, participación ... GROUP BY dim ORDER BY métrica LIMIT n", todas),
        ConsultaTotal("CQ-01", "Total del periodo",
                      "Valor agregado de una métrica para un periodo y filtros",
                      "SELECT métrica FROM fact JOIN dims WHERE periodo AND filtros", todas),
    ]
