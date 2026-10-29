"""
Modelo orientado a objetos PERSISTENTE del agente (BDOO con ZODB).

Conceptos de BDOO (clase P06) y dónde se materializan:
  - Identificador de objeto (IDO/OID) ...... ObjetoAgente.ido -> _p_oid asignado por ZODB, sin significado
                                              de negocio e inmutable.
  - Objetos complejos ....................... Sesion -> [Pregunta -> Intencion, RespuestaAgente -> ResultadoConsulta]
  - Métodos / comportamiento ................ cada clase expone operaciones (registrar, validar, render...).
  - Encapsulamiento ......................... estado en atributos "_privados"; sólo se cambia vía métodos.
  - Herencia ................................ ObjetoAgente -> Usuario -> Gerente / Analista;
                                              ConsultaAnalitica -> 5 subclases; ReglaValidacion -> 11 subclases.
  - Polimorfismo ............................ Usuario.nivel_detalle(), ConsultaAnalitica.construir_sql(),
                                              ReglaValidacion.validar(): mismo mensaje, distinta implementación.
  - Apuntadores suaves ...................... referencias entre objetos persistentes (ZODB guarda el OID y
                                              resuelve el objeto al acceder: carga perezosa).
  - LOB ..................................... ResultadoConsulta guarda la exportación CSV en un ZODB Blob.
  - TDA ..................................... agente/bdoo/tda.py (Periodo, Filtro, DocumentoIdentidad...).
  - Versionamiento .......................... ConsultaAnalitica.nueva_version() + historial de ZODB (db.history).
  - Recuperación y concurrencia ............. transacciones ACID de ZODB (commit/abort, control optimista).

La BDOO NO replica las tablas del Data Mart: guarda objetos del agente y su trazabilidad.
"""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from persistent import Persistent
from persistent.list import PersistentList
from persistent.mapping import PersistentMapping
from ZODB.blob import Blob

from agente.bdoo.tda import DocumentoIdentidad, Filtro, Periodo, ResultadoValidacion


# =============================================================================================
class ObjetoAgente(Persistent):
    """Raíz de la jerarquía persistente. Aporta identidad (IDO) y metadatos comunes."""

    def __init__(self):
        self._creado_en = datetime.now()

    @property
    def ido(self) -> str | None:
        """Identificador de objeto asignado por la BDOO (hex del OID de ZODB)."""
        oid = getattr(self, "_p_oid", None)
        return oid.hex() if oid else None

    @property
    def creado_en(self) -> datetime:
        return self._creado_en

    @property
    def clase(self) -> str:
        return type(self).__name__

    @abstractmethod
    def describir(self) -> str:
        raise NotImplementedError

    def a_dict(self) -> dict:
        """Representación para evidencias (incluye el IDO y las referencias a otros objetos por IDO)."""
        return {"clase": self.clase, "ido": self.ido, "creado_en": self._creado_en.isoformat(timespec="seconds")}

    def __repr__(self) -> str:
        return f"<{self.clase} ido={self.ido} {self.describir()}>"


def _ref(obj) -> str | None:
    """Apuntador suave expresado como IDO (para mostrarlo en evidencias)."""
    return obj.ido if isinstance(obj, ObjetoAgente) else None


# =============================================================================================
# USUARIO (herencia + polimorfismo)
# =============================================================================================
class Usuario(ObjetoAgente):
    """Quien formula las preguntas. Clase abstracta: se instancian Gerente o Analista."""

    rol = "usuario"

    def __init__(self, nombre: str, documento: str, correo: str = ""):
        if type(self) is Usuario:
            raise TypeError("Usuario es abstracta: instancie Gerente o Analista")
        super().__init__()
        self._nombre = nombre
        self._documento = DocumentoIdentidad(documento)   # TDA con validación de formato
        self._correo = correo
        self._preferencias = PersistentMapping()

    @property
    def nombre(self) -> str:
        return self._nombre

    @property
    def documento(self) -> DocumentoIdentidad:
        return self._documento

    @abstractmethod
    def nivel_detalle(self) -> str:
        """'ejecutivo' o 'tecnico' — define cómo se presenta la respuesta (polimorfismo)."""
        raise NotImplementedError

    @abstractmethod
    def muestra_sql(self) -> bool:
        raise NotImplementedError

    def definir_preferencia(self, clave: str, valor) -> None:
        self._preferencias[clave] = valor

    def preferencia(self, clave: str, defecto=None):
        return self._preferencias.get(clave, defecto)

    def describir(self) -> str:
        return f"{self.rol} {self._nombre} ({self._documento})"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "nombre": self._nombre, "documento": str(self._documento),
                "rol": self.rol, "nivel_detalle": self.nivel_detalle(), "preferencias": dict(self._preferencias)}


class Gerente(Usuario):
    rol = "gerente"

    def nivel_detalle(self) -> str:
        return "ejecutivo"

    def muestra_sql(self) -> bool:
        return False


class Analista(Usuario):
    rol = "analista"

    def nivel_detalle(self) -> str:
        return "tecnico"

    def muestra_sql(self) -> bool:
        return True


# =============================================================================================
# FUENTE DE DATO (objeto compartido: muchas respuestas apuntan al MISMO objeto)
# =============================================================================================
class FuenteDato(ObjetoAgente):
    def __init__(self, sistema: str, tabla: str, tipo: str, campos: tuple, descripcion: str = ""):
        super().__init__()
        self._sistema = sistema
        self._tabla = tabla
        self._tipo = tipo
        self._campos = tuple(campos)
        self._descripcion = descripcion
        self._usos = 0

    @property
    def tabla(self) -> str:
        return self._tabla

    @property
    def tipo(self) -> str:
        return self._tipo

    @property
    def campos(self) -> tuple:
        return self._campos

    @property
    def usos(self) -> int:
        return self._usos

    def registrar_uso(self) -> None:
        self._usos += 1

    def describir(self) -> str:
        return f"{self._tipo} {self._tabla} ({self._sistema})"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "sistema": self._sistema, "tabla": self._tabla, "tipo": self._tipo,
                "campos": list(self._campos), "usos": self._usos}


# =============================================================================================
# INTENCIÓN
# =============================================================================================
class Intencion(ObjetoAgente):
    """Necesidad analítica identificada a partir de la pregunta."""

    TIPOS = ("consulta", "ambigua", "fuera_de_alcance", "dimension_inexistente", "operacion_no_autorizada",
             "faltan_parametros")

    def __init__(self, tipo: str, nombre: str | None = None, operacion: str | None = None,
                 metrica: str | None = None, dimension: str | None = None, periodo: Periodo | None = None,
                 periodo_comparacion: Periodo | None = None, filtros: list[Filtro] | None = None,
                 orden: str = "desc", limite: int | None = None, desglose: str | None = None,
                 origen: str = "reglas", dimension_texto: str | None = None, opciones: list | None = None,
                 faltantes: list | None = None, motivo: str = "", datos_crudos: dict | None = None,
                 supuestos: list | None = None):
        super().__init__()
        if tipo not in self.TIPOS:
            raise ValueError(f"Tipo de intención inválido: {tipo}")
        self._tipo = tipo
        self._nombre = nombre
        self._operacion = operacion
        self._metrica = metrica
        self._dimension = dimension
        self._periodo = periodo
        self._periodo_comparacion = periodo_comparacion
        self._filtros = list(filtros or [])
        self._orden = orden if orden in ("asc", "desc") else "desc"
        self._limite = limite
        self._desglose = desglose
        self._origen = origen
        self._dimension_texto = dimension_texto
        self._opciones = list(opciones or [])
        self._faltantes = list(faltantes or [])
        self._motivo = motivo
        self._datos_crudos = dict(datos_crudos or {})
        self._supuestos = PersistentList(supuestos or [])

    # -- lectura (encapsulamiento: no hay setters públicos) --------------------------------------
    tipo = property(lambda s: s._tipo)
    nombre = property(lambda s: s._nombre)
    operacion = property(lambda s: s._operacion)
    metrica = property(lambda s: s._metrica)
    dimension = property(lambda s: s._dimension)
    periodo = property(lambda s: s._periodo)
    periodo_comparacion = property(lambda s: s._periodo_comparacion)
    filtros = property(lambda s: tuple(s._filtros))
    orden = property(lambda s: s._orden)
    limite = property(lambda s: s._limite)
    desglose = property(lambda s: s._desglose)
    origen = property(lambda s: s._origen)
    dimension_texto = property(lambda s: s._dimension_texto)
    opciones = property(lambda s: tuple(s._opciones))
    faltantes = property(lambda s: tuple(s._faltantes))
    motivo = property(lambda s: s._motivo)
    supuestos = property(lambda s: tuple(s._supuestos))

    # -- comportamiento --------------------------------------------------------------------------
    def es_ejecutable(self) -> bool:
        return self._tipo == "consulta" and self._metrica is not None and self._periodo is not None

    def ajustar_periodo(self, periodo: Periodo, supuesto: str | None = None) -> None:
        self._periodo = periodo
        if supuesto:
            self._supuestos.append(supuesto)

    def ajustar_periodo_comparacion(self, periodo: Periodo | None) -> None:
        self._periodo_comparacion = periodo

    def registrar_supuesto(self, texto: str) -> None:
        self._supuestos.append(texto)

    def reclasificar(self, tipo: str, motivo: str = "", opciones: list | None = None) -> None:
        if tipo not in self.TIPOS:
            raise ValueError(tipo)
        self._tipo = tipo
        self._motivo = motivo or self._motivo
        if opciones is not None:
            self._opciones = list(opciones)

    def filtro_de(self, dimension: str) -> Filtro | None:
        return next((f for f in self._filtros if f.dimension == dimension), None)

    def describir(self) -> str:
        if self._tipo != "consulta":
            return f"[{self._tipo}] {self._motivo}".strip()
        partes = [f"intención={self._nombre}", f"operación={self._operacion}", f"métrica={self._metrica}",
                  f"dimensión={self._dimension or '—'}", f"periodo={self._periodo}"]
        if self._periodo_comparacion:
            partes.append(f"vs={self._periodo_comparacion}")
        if self._filtros:
            partes.append("filtros=" + "; ".join(f.describir() for f in self._filtros))
        partes.append(f"orden={self._orden}")
        if self._limite:
            partes.append(f"límite={self._limite}")
        return " | ".join(partes)

    def a_dict(self) -> dict:
        return {**super().a_dict(), "tipo": self._tipo, "intencion": self._nombre, "operacion": self._operacion,
                "metrica": self._metrica, "dimension": self._dimension,
                "periodo": self._periodo.a_dict() if self._periodo else None,
                "periodo_comparacion": self._periodo_comparacion.a_dict() if self._periodo_comparacion else None,
                "filtros": [f.a_dict() for f in self._filtros], "orden": self._orden, "limite": self._limite,
                "desglose": self._desglose, "origen": self._origen, "dimension_texto": self._dimension_texto,
                "opciones": list(self._opciones), "faltantes": list(self._faltantes), "motivo": self._motivo,
                "supuestos": list(self._supuestos)}


# =============================================================================================
# RESULTADO DE CONSULTA (incluye un LOB)
# =============================================================================================
class ResultadoConsulta(ObjetoAgente):
    MAX_FILAS_GUARDADAS = 500

    def __init__(self, consulta, sql: str, parametros: dict, columnas: list[str], filas: list[tuple],
                 duracion_ms: float, error: str | None = None):
        super().__init__()
        self._consulta = consulta                    # apuntador suave a ConsultaAnalitica
        self._sql = sql
        self._parametros = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in (parametros or {}).items()}
        self._columnas = list(columnas)
        self._n_filas = len(filas)
        self._filas = PersistentList(filas[: self.MAX_FILAS_GUARDADAS])
        self._duracion_ms = round(duracion_ms, 2)
        self._error = error
        self._ejecutado_en = datetime.now()
        self._csv = None                              # ZODB Blob (LOB) con la exportación completa
        if filas:
            self._guardar_csv(columnas, filas)

    def _guardar_csv(self, columnas, filas) -> None:
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(columnas)
        w.writerows(filas)
        self._csv = Blob()
        with self._csv.open("w") as f:
            f.write(buf.getvalue().encode("utf-8"))

    consulta = property(lambda s: s._consulta)
    sql = property(lambda s: s._sql)
    parametros = property(lambda s: dict(s._parametros))
    columnas = property(lambda s: list(s._columnas))
    filas = property(lambda s: list(s._filas))
    n_filas = property(lambda s: s._n_filas)
    duracion_ms = property(lambda s: s._duracion_ms)
    error = property(lambda s: s._error)

    def esta_vacio(self) -> bool:
        return self._n_filas == 0

    def tiene_error(self) -> bool:
        return self._error is not None

    def indice(self, columna: str) -> int:
        return self._columnas.index(columna)

    def columna(self, nombre: str) -> list:
        i = self.indice(nombre)
        return [f[i] for f in self._filas]

    def como_dicts(self) -> list[dict]:
        return [dict(zip(self._columnas, f)) for f in self._filas]

    def leer_csv(self) -> str:
        """Lee el LOB asociado."""
        if self._csv is None:
            return ""
        with self._csv.open("r") as f:
            return f.read().decode("utf-8")

    def describir(self) -> str:
        return f"{self._n_filas} fila(s) en {self._duracion_ms} ms" + (f" ERROR {self._error}" if self._error else "")

    def a_dict(self) -> dict:
        return {**super().a_dict(), "consulta_ido": _ref(self._consulta), "sql": self._sql,
                "parametros": self._parametros, "columnas": self._columnas, "n_filas": self._n_filas,
                "filas_muestra": [list(f) for f in self._filas[:10]], "duracion_ms": self._duracion_ms,
                "error": self._error, "lob_csv_bytes": len(self.leer_csv().encode()) if self._csv else 0}


# =============================================================================================
# RESPUESTA DEL AGENTE
# =============================================================================================
class RespuestaAgente(ObjetoAgente):
    TIPOS = ("RESPUESTA", "SIN_DATOS", "ACLARACION", "RECHAZO", "ERROR")

    def __init__(self, tipo: str, resumen: str):
        super().__init__()
        if tipo not in self.TIPOS:
            raise ValueError(tipo)
        self._tipo = tipo
        self._resumen = resumen
        self._interpretacion = ""
        self._origen_interpretacion = "plantilla"
        self._metrica = ""
        self._regla_calculo = ""
        self._periodo = ""
        self._filtros = ""
        self._dimension = ""
        self._consulta_codigo = ""
        self._sql = ""
        self._parametros = {}
        self._fuentes = PersistentList()            # apuntadores a objetos FuenteDato compartidos
        self._resultado = None                      # apuntador a ResultadoConsulta
        self._advertencias = PersistentList()
        self._validaciones = PersistentList()
        self._opciones = PersistentList()

    tipo = property(lambda s: s._tipo)
    resumen = property(lambda s: s._resumen)
    interpretacion = property(lambda s: s._interpretacion)
    origen_interpretacion = property(lambda s: s._origen_interpretacion)
    resultado = property(lambda s: s._resultado)
    fuentes = property(lambda s: list(s._fuentes))
    advertencias = property(lambda s: list(s._advertencias))
    validaciones = property(lambda s: [dict(v) for v in s._validaciones])
    opciones = property(lambda s: list(s._opciones))
    sql = property(lambda s: s._sql)
    parametros = property(lambda s: dict(s._parametros))
    metrica = property(lambda s: s._metrica)
    regla_calculo = property(lambda s: s._regla_calculo)
    periodo = property(lambda s: s._periodo)
    filtros = property(lambda s: s._filtros)
    dimension = property(lambda s: s._dimension)
    consulta_codigo = property(lambda s: s._consulta_codigo)

    def cambiar_tipo(self, tipo: str, resumen: str | None = None) -> None:
        if tipo not in self.TIPOS:
            raise ValueError(tipo)
        self._tipo = tipo
        if resumen:
            self._resumen = resumen

    def documentar_metrica(self, nombre: str, regla: str) -> None:
        self._metrica, self._regla_calculo = nombre, regla

    def documentar_contexto(self, periodo: str, filtros: str, dimension: str) -> None:
        self._periodo, self._filtros, self._dimension = periodo, filtros, dimension

    def documentar_consulta(self, codigo: str, sql: str, parametros: dict) -> None:
        self._consulta_codigo, self._sql = codigo, sql
        self._parametros = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in parametros.items()}

    def asignar_interpretacion(self, texto: str, origen: str = "plantilla") -> None:
        self._interpretacion, self._origen_interpretacion = texto, origen

    def asignar_resultado(self, resultado: ResultadoConsulta) -> None:
        self._resultado = resultado

    def agregar_fuente(self, fuente: FuenteDato) -> None:
        if fuente not in self._fuentes:
            self._fuentes.append(fuente)
            fuente.registrar_uso()

    def agregar_advertencia(self, texto: str) -> None:
        if texto and texto not in self._advertencias:
            self._advertencias.append(texto)

    def registrar_validacion(self, rv: ResultadoValidacion) -> None:
        self._validaciones.append(PersistentMapping(rv.a_dict()))

    def definir_opciones(self, opciones: list[str]) -> None:
        self._opciones = PersistentList(opciones)

    def describir(self) -> str:
        return f"{self._tipo}: {self._resumen[:80]}"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "tipo": self._tipo, "resumen": self._resumen,
                "interpretacion": self._interpretacion, "origen_interpretacion": self._origen_interpretacion,
                "metrica": self._metrica, "regla_calculo": self._regla_calculo, "periodo": self._periodo,
                "filtros": self._filtros, "dimension": self._dimension, "consulta": self._consulta_codigo,
                "sql": self._sql, "parametros": self._parametros, "fuentes_ido": [_ref(f) for f in self._fuentes],
                "fuentes": [f.tabla for f in self._fuentes], "resultado_ido": _ref(self._resultado),
                "advertencias": list(self._advertencias), "validaciones": [dict(v) for v in self._validaciones],
                "opciones": list(self._opciones)}


# =============================================================================================
# PREGUNTA (máquina de estados)
# =============================================================================================
class Pregunta(ObjetoAgente):
    TRANSICIONES = {
        "RECIBIDA": {"INTERPRETADA", "RECHAZADA", "ERROR"},
        "INTERPRETADA": {"RESPONDIDA", "SIN_DATOS", "ACLARACION", "RECHAZADA", "ERROR"},
        "RESPONDIDA": set(), "SIN_DATOS": set(), "ACLARACION": set(), "RECHAZADA": set(), "ERROR": set(),
    }

    def __init__(self, texto: str, sesion: "Sesion"):
        super().__init__()
        if not texto or not texto.strip():
            raise ValueError("La pregunta no puede estar vacía")
        self._texto = texto.strip()
        self._sesion = sesion                    # referencia inversa (apuntador suave)
        self._fecha = datetime.now()
        self._estado = "RECIBIDA"
        self._historial_estados = PersistentList([("RECIBIDA", self._fecha.isoformat(timespec="seconds"))])
        self._intencion: Intencion | None = None
        self._respuesta: RespuestaAgente | None = None
        self._es_seguimiento = False

    texto = property(lambda s: s._texto)
    fecha = property(lambda s: s._fecha)
    estado = property(lambda s: s._estado)
    sesion = property(lambda s: s._sesion)
    intencion = property(lambda s: s._intencion)
    respuesta = property(lambda s: s._respuesta)
    es_seguimiento = property(lambda s: s._es_seguimiento)

    @property
    def filtros(self) -> tuple:
        return self._intencion.filtros if self._intencion else ()

    def cambiar_estado(self, nuevo: str) -> None:
        if nuevo not in self.TRANSICIONES.get(self._estado, set()):
            raise ValueError(f"Transición inválida {self._estado} -> {nuevo}")
        self._estado = nuevo
        self._historial_estados.append((nuevo, datetime.now().isoformat(timespec="seconds")))

    def asignar_intencion(self, intencion: Intencion, seguimiento: bool = False) -> None:
        self._intencion = intencion
        self._es_seguimiento = seguimiento
        self.cambiar_estado("INTERPRETADA")

    def asignar_respuesta(self, respuesta: RespuestaAgente) -> None:
        self._respuesta = respuesta
        estado = {"RESPUESTA": "RESPONDIDA", "SIN_DATOS": "SIN_DATOS", "ACLARACION": "ACLARACION",
                  "RECHAZO": "RECHAZADA", "ERROR": "ERROR"}[respuesta.tipo]
        if self._estado == "RECIBIDA" and estado not in self.TRANSICIONES["RECIBIDA"]:
            self.cambiar_estado("INTERPRETADA")
        self.cambiar_estado(estado)

    def describir(self) -> str:
        return f"[{self._estado}] {self._texto[:70]}"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "texto": self._texto, "fecha": self._fecha.isoformat(timespec="seconds"),
                "estado": self._estado, "historial_estados": [list(e) for e in self._historial_estados],
                "sesion_ido": _ref(self._sesion), "intencion_ido": _ref(self._intencion),
                "respuesta_ido": _ref(self._respuesta), "es_seguimiento": self._es_seguimiento}


# =============================================================================================
# SESIÓN (memoria operativa)
# =============================================================================================
class Sesion(ObjetoAgente):
    def __init__(self, codigo: str, usuario: Usuario, titulo: str = ""):
        super().__init__()
        self._codigo = codigo
        self._usuario = usuario
        self._titulo = titulo or f"Sesión {codigo}"
        self._inicio = datetime.now()
        self._fin: datetime | None = None
        self._preguntas = PersistentList()
        self._contexto = PersistentMapping()    # memoria operativa: última intención consultable

    codigo = property(lambda s: s._codigo)
    usuario = property(lambda s: s._usuario)
    titulo = property(lambda s: s._titulo)
    inicio = property(lambda s: s._inicio)
    fin = property(lambda s: s._fin)
    preguntas = property(lambda s: list(s._preguntas))

    @property
    def activa(self) -> bool:
        return self._fin is None

    def nueva_pregunta(self, texto: str) -> Pregunta:
        if not self.activa:
            raise ValueError("La sesión está cerrada")
        p = Pregunta(texto, self)
        self._preguntas.append(p)
        return p

    def recordar(self, intencion: Intencion) -> None:
        """Guarda la última intención ejecutable para resolver preguntas de seguimiento ('¿y en 2025?')."""
        if intencion.es_ejecutable():
            self._contexto["ultima_intencion"] = intencion

    def contexto(self) -> dict:
        return dict(self._contexto)

    def cerrar(self) -> None:
        self._fin = datetime.now()

    def resumen(self) -> dict:
        estados = {}
        for p in self._preguntas:
            estados[p.estado] = estados.get(p.estado, 0) + 1
        return {"preguntas": len(self._preguntas), "por_estado": estados}

    def describir(self) -> str:
        return f"{self._codigo} de {self._usuario.nombre} ({len(self._preguntas)} preguntas)"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "codigo": self._codigo, "titulo": self._titulo, "usuario_ido": _ref(self._usuario),
                "inicio": self._inicio.isoformat(timespec="seconds"),
                "fin": self._fin.isoformat(timespec="seconds") if self._fin else None,
                "preguntas_ido": [_ref(p) for p in self._preguntas],
                "contexto": {k: _ref(v) for k, v in self._contexto.items()}, "resumen": self.resumen()}
