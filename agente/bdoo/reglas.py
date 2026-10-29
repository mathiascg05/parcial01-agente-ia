"""
Reglas de validación (ReglaValidacion y subclases): controles aplicados ANTES de responder.

Patrón Chain of Responsibility: el agente recorre la cadena de reglas activas de cada "momento"
(texto -> intención -> sql -> resultado -> narrativa). Cada regla implementa validar() de forma
distinta (polimorfismo) y devuelve un ResultadoValidacion (TDA). Una regla 'bloqueante' que falla
detiene el flujo; una 'advertencia' se agrega a la respuesta.
"""
from __future__ import annotations

import re
from abc import abstractmethod
from dataclasses import dataclass, field

from agente.bdoo.modelo import ObjetoAgente
from agente.bdoo.tda import ResultadoValidacion
from agente.catalogo import DIMENSIONES, METRICAS, TABLAS_AUTORIZADAS
from agente.datamart import normalizar


@dataclass
class ContextoValidacion:
    """Objeto volátil (no persistente) que viaja por la cadena de reglas."""
    texto: str
    metadatos: object = None
    intencion: object = None
    sql: str | None = None
    parametros: dict = field(default_factory=dict)
    resultado: object = None
    narrativa: str | None = None
    control_total: float | None = None


class ReglaValidacion(ObjetoAgente):
    MOMENTOS = ("texto", "intencion", "sql", "resultado", "narrativa")

    def __init__(self, codigo: str, nombre: str, descripcion: str, momento: str, severidad: str):
        if type(self) is ReglaValidacion:
            raise TypeError("ReglaValidacion es abstracta")
        super().__init__()
        assert momento in self.MOMENTOS
        self._codigo = codigo
        self._nombre = nombre
        self._descripcion = descripcion
        self._momento = momento
        self._severidad = severidad
        self._activa = True
        self._evaluaciones = 0
        self._fallos = 0

    codigo = property(lambda s: s._codigo)
    nombre = property(lambda s: s._nombre)
    descripcion = property(lambda s: s._descripcion)
    momento = property(lambda s: s._momento)
    severidad = property(lambda s: s._severidad)
    activa = property(lambda s: s._activa)
    evaluaciones = property(lambda s: s._evaluaciones)
    fallos = property(lambda s: s._fallos)

    def activar(self, valor: bool = True) -> None:
        self._activa = valor

    def aplicar(self, ctx: ContextoValidacion) -> ResultadoValidacion | None:
        """Método plantilla: lleva estadísticas y delega en validar() (polimórfico)."""
        if not self._activa:
            return None
        res = self.validar(ctx)
        if res is None:
            return None
        self._evaluaciones += 1
        if not res.aprobada:
            self._fallos += 1
        return res

    @abstractmethod
    def validar(self, ctx: ContextoValidacion) -> ResultadoValidacion | None:
        raise NotImplementedError

    def _ok(self, mensaje: str) -> ResultadoValidacion:
        return ResultadoValidacion(self._codigo, self._nombre, True, "info", mensaje, self._momento)

    def _falla(self, mensaje: str, severidad: str | None = None) -> ResultadoValidacion:
        return ResultadoValidacion(self._codigo, self._nombre, False, severidad or self._severidad, mensaje, self._momento)

    def describir(self) -> str:
        return f"{self._codigo} {self._nombre} ({self._momento}, {self._severidad})"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "codigo": self._codigo, "nombre": self._nombre, "momento": self._momento,
                "severidad": self._severidad, "activa": self._activa, "evaluaciones": self._evaluaciones,
                "fallos": self._fallos, "descripcion": self._descripcion}


# ------------------------------------------------------------------------------- momento: texto
class ReglaOperacionNoAutorizada(ReglaValidacion):
    """Bloquea pedidos de escritura/DDL, inyección SQL, credenciales o acceso a datos no autorizados.
    Distingue una ORDEN destructiva («Borra las ventas de enero») de una PREGUNTA de negocio que usa el mismo
    verbo («¿Qué productos debemos eliminar del catálogo por su bajo margen?»)."""
    SIEMPRE = [   # se bloquean en cualquier contexto
        (r"\b(drop|truncate|alter)\s+(table|schema|database|role|view|index)\b|\bdelete\s+from\b|\bupdate\s+[\w\.]+\s+set\b|"
         r"\binsert\s+into\b|\bgrant\b\s+\w+|\brevoke\b\s+\w+|\bcreate\s+(table|role|user|view|function)\b", "instrucción SQL de escritura o DDL"),
        (r";\s*(drop|delete|update|insert|select|truncate|alter|grant|create|with)\b|--|/\*|\bunion\s+(all\s+)?select\b|"
         r"\bpg_\w+|information_schema|\boltp\.|\bcontrol\.", "inyección SQL / esquemas no autorizados"),
        (r"(contrasen\w*|password|credencial\w*|clave de acceso|api ?key|\btoken\b|cadena de conexion)", "obtener credenciales"),
        (r"\b(ignora|olvida|omite) (tus|las|todas las) (instrucciones|reglas|restricciones)", "manipulación de instrucciones"),
        (r"\b(ejecuta|corre|lanza)\b.*\b(sql|comando|script|query)\b", "ejecutar código arbitrario"),
    ]
    VERBOS = (r"borr\w*|elimin\w*|suprim\w*|actualiz\w*|modific\w*|cambi(a|ar|en)\b|edit(a|ar)\b|sobrescrib\w*|"
              r"insert\w*|agreg(a|ar)\b|anad(e|ir)\b|registr(a|ar)\b|crea(r)?\b|vaci(a|ar)\b|purg\w*|resete\w*|reinici\w*|"
              r"restaur\w*|carg(a|ar)\b|sub(e|ir)\b|ajust(a|ar)\b|corrig(e|ir)\b|duplic(a|ar)\b|deshac\w*|limpi(a|ar)\b|"
              r"drop|delete|update|insert|truncate")
    OBJETOS = r"(ventas?|registros?|datos|tablas?|filas?|tickets?|clientes?|productos?|precios?|base de datos|data ?mart|hechos?|dimension\w*|historial|todo)"
    INTERROGATIVO = r"^(que|cual|cuales|como|cuanto|cuantos|cuantas|donde|cuando|por que|deberia\w*|debemos|conviene|vale la pena|es recomendable)\b"

    def __init__(self):
        super().__init__("RV01", "Operación autorizada (sólo lectura)",
                         "Rechaza órdenes de escritura o DDL, credenciales, inyección SQL o acceso a esquemas distintos "
                         "de dm. Las preguntas de negocio que mencionan esos verbos se permiten.", "texto", "bloqueante")

    def validar(self, ctx):
        crudo = ctx.texto.lower()
        t = normalizar(ctx.texto).replace("¿", "").replace("¡", "").strip(" ?!.")
        for patron, motivo in self.SIEMPRE:
            if re.search(patron, crudo) or re.search(patron, t):
                return self._falla(f"Operación no autorizada ({motivo}). El agente sólo realiza consultas de "
                                   f"lectura sobre el Data Mart de ventas.")
        if not re.search(self.INTERROGATIVO, t):
            orden = re.search(rf"^(por favor\s+)?((puedes|podrias|quiero|necesito|hay que|vamos a|procede a|favor)\s+)?({self.VERBOS})", t)
            sobre_datos = re.search(rf"\b({self.VERBOS})\b.{{0,40}}\b{self.OBJETOS}", t)
            if orden or sobre_datos:
                return self._falla("Operación no autorizada (modificar o eliminar datos). El agente sólo realiza consultas "
                                   "de lectura sobre el Data Mart de ventas.")
        return self._ok("Solicitud de sólo lectura")


# --------------------------------------------------------------------------- momento: intención
class ReglaAlcanceDataMart(ReglaValidacion):
    def __init__(self):
        super().__init__("RV02", "Alcance del Data Mart",
                         "La pregunta debe referirse a métricas del Data Mart de ventas; si no, se declara fuera "
                         "de alcance sin inventar información.", "intencion", "bloqueante")

    def validar(self, ctx):
        i = ctx.intencion
        if i.tipo == "fuera_de_alcance":
            return self._falla(i.motivo or "La pregunta está fuera del alcance del Data Mart de ventas.")
        if i.tipo == "consulta" and i.metrica not in METRICAS:
            return self._falla(f"Métrica '{i.metrica}' no existe en el catálogo.")
        return self._ok("Pregunta dentro del alcance")


class ReglaDimensionExistente(ReglaValidacion):
    def __init__(self):
        super().__init__("RV03", "Dimensión existente",
                         "La dimensión solicitada debe existir en el modelo dimensional.", "intencion", "bloqueante")

    def validar(self, ctx):
        i = ctx.intencion
        if i.tipo == "dimension_inexistente":
            return self._falla(f"La dimensión '{i.dimension_texto}' no existe en el Data Mart.")
        for d in [i.dimension, i.desglose, *[f.dimension for f in i.filtros]]:
            if d and d not in DIMENSIONES:
                return self._falla(f"La dimensión '{d}' no existe en el Data Mart.")
        return self._ok("Dimensiones válidas")


class ReglaCriterioExplicito(ReglaValidacion):
    def __init__(self):
        super().__init__("RV04", "Criterio explícito (ambigüedad)",
                         "Si la pregunta no define el criterio (p. ej. 'mejor canal') o faltan parámetros, el agente "
                         "solicita aclaración en vez de suponer.", "intencion", "bloqueante")

    def validar(self, ctx):
        i = ctx.intencion
        if i.tipo == "ambigua":
            return self._falla(i.motivo or "La pregunta es ambigua: falta el criterio de evaluación.")
        if i.tipo == "faltan_parametros":
            return self._falla(i.motivo or f"Faltan parámetros: {', '.join(i.faltantes)}.")
        return self._ok("Criterio explícito")


class ReglaValoresFiltro(ReglaValidacion):
    def __init__(self):
        super().__init__("RV05", "Valores de filtro existentes",
                         "Cada valor de filtro debe existir en la dimensión correspondiente del Data Mart.",
                         "intencion", "bloqueante")

    def validar(self, ctx):
        i, meta = ctx.intencion, ctx.metadatos
        if i.tipo != "consulta" or meta is None:
            return None
        for f in i.filtros:
            for v in f.valores:
                if meta.resolver_valor(f.dimension, v) is None:
                    sug = meta.sugerencias(f.dimension, v)
                    extra = f" ¿Quiso decir: {', '.join(sug)}?" if sug else \
                        f" Valores disponibles: {', '.join(meta.opciones(f.dimension))}."
                    return self._falla(f"El valor '{v}' no existe en la dimensión {DIMENSIONES[f.dimension].nombre}.{extra}")
        return self._ok("Valores de filtro verificados contra el Data Mart")


class ReglaPeriodoDisponible(ReglaValidacion):
    def __init__(self):
        super().__init__("RV06", "Periodo disponible",
                         "Explicita el periodo asumido y advierte si el periodo pedido está fuera (total o "
                         "parcialmente) del rango cargado en el Data Mart.", "intencion", "advertencia")

    def validar(self, ctx):
        i, meta = ctx.intencion, ctx.metadatos
        if i.tipo != "consulta" or i.periodo is None or meta is None:
            return None
        rango = f"{meta.fecha_min:%d-%m-%Y} a {meta.fecha_max:%d-%m-%Y}"
        for p in [i.periodo, i.periodo_comparacion]:
            if p is None:
                continue
            if p.hasta < meta.fecha_min or p.desde > meta.fecha_max:
                return self._falla(f"El periodo {p} está fuera del rango disponible en el Data Mart ({rango}).")
            if p.desde < meta.fecha_min or p.hasta > meta.fecha_max:
                return self._falla(f"El periodo {p} sólo está cubierto parcialmente (datos disponibles {rango}).")
        if not i.periodo.explicito:
            return self._falla(f"La pregunta no indica periodo: se usó todo el rango disponible ({rango}).")
        return self._ok(f"Periodo dentro del rango disponible ({rango})")


# --------------------------------------------------------------------------------- momento: sql
class ReglaSQLSoloLectura(ReglaValidacion):
    PROHIBIDAS = r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|execute|call|do|into|" \
                 r"vacuum|analyze|lock|set|reset|commit|rollback|pg_sleep|pg_read_file|lo_import|dblink)\b"

    def __init__(self):
        super().__init__("RV07", "SQL seguro de sólo lectura",
                         "El SQL final debe ser una única sentencia SELECT/WITH, sin palabras prohibidas y sólo "
                         "sobre tablas autorizadas del esquema dm.", "sql", "bloqueante")

    def validar(self, ctx):
        sql = (ctx.sql or "").strip()
        bajo = re.sub(r"'[^']*'", "''", sql.lower())       # ignora literales
        if not re.match(r"^(select|with)\b", bajo):
            return self._falla("El SQL no inicia con SELECT/WITH.")
        if ";" in bajo or "--" in bajo or "/*" in bajo:
            return self._falla("El SQL contiene múltiples sentencias o comentarios.")
        m = re.search(self.PROHIBIDAS, bajo)
        if m:
            return self._falla(f"El SQL contiene una instrucción no permitida: '{m.group(1)}'.")
        ctes = set(re.findall(r"(?:with|,)\s*([a-z_]\w*)\s+as\s*\(", bajo))
        tablas = set(re.findall(r"\b(?:from|join)\s+([a-z_][\w\.]*)", bajo))
        no_aut = {t for t in tablas if t not in TABLAS_AUTORIZADAS and t not in ctes}
        if no_aut:
            return self._falla(f"El SQL referencia tablas no autorizadas: {', '.join(sorted(no_aut))}.")
        return self._ok(f"SELECT sobre tablas autorizadas: {', '.join(sorted(tablas - ctes))}")


# --------------------------------------------------------------------------- momento: resultado
class ReglaResultadoNoVacio(ReglaValidacion):
    def __init__(self):
        super().__init__("RV08", "Resultado con registros",
                         "Si la consulta no devuelve registros se informa 'sin datos' (no se convierte en cero).",
                         "resultado", "bloqueante")

    def validar(self, ctx):
        r = ctx.resultado
        if r.tiene_error():
            return self._falla(f"Error al ejecutar la consulta: {r.error}")
        if r.esta_vacio():
            return self._falla("La consulta no devolvió registros para los criterios indicados.")
        return self._ok(f"{r.n_filas} fila(s) devueltas")


class ReglaMiembrosDesconocidos(ReglaValidacion):
    ETIQUETAS = ("no informado", "no informada", "sin correspondencia", "consumidor final")

    def __init__(self):
        super().__init__("RV09", "Miembros desconocidos",
                         "Advierte cuando el resultado incluye ventas asignadas a miembros 'No informado' o "
                         "'Sin correspondencia' (claves faltantes o huérfanas en la fuente).", "resultado", "advertencia")

    def validar(self, ctx):
        r, i = ctx.resultado, ctx.intencion
        if r.esta_vacio() or not i.dimension:
            return None
        col = i.dimension if i.dimension in r.columnas else None
        if not col:
            return None
        encontrados = sorted({str(v) for v in r.columna(col) if any(e in str(v).lower() for e in self.ETIQUETAS)})
        if encontrados:
            return self._falla(f"El resultado incluye miembros especiales ({', '.join(encontrados)}): corresponden a "
                               f"ventas cuya clave venía vacía o sin correspondencia en la fuente; se muestran por "
                               f"separado para no perder ingresos.")
        return self._ok("Sin miembros desconocidos en el resultado")


class ReglaConsistenciaTotales(ReglaValidacion):
    def __init__(self):
        super().__init__("RV10", "Consistencia de totales",
                         "Para métricas aditivas sin límite, la suma de las filas debe igualar el total "
                         "calculado por una consulta de control independiente.", "resultado", "advertencia")

    def validar(self, ctx):
        r, i = ctx.resultado, ctx.intencion
        if ctx.control_total is None or r.esta_vacio() or i.metrica not in r.columnas:
            return None
        suma = round(sum(v or 0 for v in r.columna(i.metrica)), 2)
        if abs(suma - round(ctx.control_total, 2)) <= 0.01:
            return self._ok(f"Suma de filas = total de control ({suma:,.2f})")
        return self._falla(f"La suma de filas ({suma:,.2f}) no coincide con el total de control ({ctx.control_total:,.2f}).")


# --------------------------------------------------------------------------- momento: narrativa
class ReglaNarrativaRespaldada(ReglaValidacion):
    def __init__(self):
        super().__init__("RV11", "Narrativa respaldada por datos",
                         "Toda cifra mencionada por el LLM en la interpretación debe existir en el resultado; si no, "
                         "se descarta la narrativa del LLM y se usa la plantilla determinista.", "narrativa", "advertencia")

    @staticmethod
    def _numeros(texto: str) -> list[float]:
        nums = []
        for n in re.findall(r"-?\d[\d\.,]*", texto):
            s = n.strip(".,")
            if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s):          # 1.234.567,89
                s = s.replace(".", "").replace(",", ".")
            elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):        # 1,234,567.89
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
            try:
                nums.append(float(s))
            except ValueError:
                pass
        return nums

    def validar(self, ctx):
        if not ctx.narrativa or ctx.resultado is None:
            return None
        valores = []
        for fila in ctx.resultado.filas:
            for v in fila:
                if isinstance(v, (int, float)):
                    valores.append(float(v))
                elif v is not None:
                    valores += self._numeros(str(v))
        if valores:
            total = sum(abs(v) for v in valores)
            valores.append(total)
        no_respaldados = []
        for n in self._numeros(ctx.narrativa):
            if abs(n) < 10 and float(n).is_integer():       # ordinales, "5 categorías", años cortos
                continue
            if 1990 <= n <= 2100 and float(n).is_integer():  # años
                continue
            if not any(abs(n - v) <= max(0.6, abs(v) * 0.006) or abs(abs(n) - abs(v)) <= max(0.6, abs(v) * 0.006)
                       for v in valores):
                no_respaldados.append(n)
        if no_respaldados:
            return self._falla(f"La narrativa del LLM menciona cifras no presentes en el resultado: "
                               f"{', '.join(str(x) for x in no_respaldados[:5])}. Se usó la interpretación por plantilla.")
        return self._ok("Todas las cifras de la narrativa están respaldadas por el resultado")


def crear_reglas() -> list[ReglaValidacion]:
    return [ReglaOperacionNoAutorizada(), ReglaAlcanceDataMart(), ReglaDimensionExistente(), ReglaCriterioExplicito(),
            ReglaValoresFiltro(), ReglaPeriodoDisponible(), ReglaSQLSoloLectura(), ReglaResultadoNoVacio(),
            ReglaMiembrosDesconocidos(), ReglaConsistenciaTotales(), ReglaNarrativaRespaldada()]
