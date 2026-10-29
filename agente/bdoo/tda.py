"""
Tipos de Datos Abstractos (TDA) del agente.

Son objetos-VALOR inmutables (sin identidad propia / sin OID): se almacenan embebidos dentro de
los objetos persistentes que los contienen. Igual que el TDA DATOS del ejemplo de Oracle visto en
clase (STATIC FUNCTION formato), cada TDA trae sus propias operaciones y su método de validación,
de modo que es imposible construir un valor inválido.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


class ErrorTDA(ValueError):
    """Violación de la regla de validación de un TDA."""


# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DocumentoIdentidad:
    """Cédula o RIF venezolano. Equivalente Python del TDA DATOS(..., rif) con su método formato()."""
    valor: str

    PATRON = re.compile(r"^[VEJGP]-\d{6,9}(-\d)?$")

    def __post_init__(self):
        object.__setattr__(self, "valor", DocumentoIdentidad.formato(self.valor))

    @staticmethod
    def formato(texto: str) -> str:
        """Valida y normaliza el documento (V-, E-, J-, G-, P-). Lanza ErrorTDA si es inválido."""
        t = (texto or "").strip().upper().replace(" ", "")
        if not DocumentoIdentidad.PATRON.match(t):
            raise ErrorTDA(f"Formato de documento inválido: '{texto}' (esperado V-12345678 o J-12345678-9)")
        return t

    @property
    def tipo(self) -> str:
        return {"V": "Venezolano", "E": "Extranjero", "J": "Jurídico", "G": "Gubernamental", "P": "Pasaporte"}[self.valor[0]]

    def __str__(self) -> str:
        return self.valor


# ---------------------------------------------------------------------------------------------
def _fin_de_mes(d: date) -> date:
    siguiente = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return siguiente - timedelta(days=1)


def etiqueta_mes(d: date) -> str:
    return f"{MESES_CORTOS[d.month - 1]}-{d.year}"


@dataclass(frozen=True)
class Periodo:
    """Intervalo cerrado de fechas [desde, hasta] con una etiqueta legible."""
    desde: date
    hasta: date
    etiqueta: str = ""
    explicito: bool = True      # False cuando el agente lo asumió (pregunta sin periodo)

    def __post_init__(self):
        Periodo.validar(self.desde, self.hasta)
        if not self.etiqueta:
            object.__setattr__(self, "etiqueta", self._etiqueta_auto())

    @staticmethod
    def validar(desde: date, hasta: date) -> None:
        if not isinstance(desde, date) or not isinstance(hasta, date):
            raise ErrorTDA("Las fechas del periodo deben ser de tipo date")
        if desde > hasta:
            raise ErrorTDA(f"Periodo inválido: {desde} es posterior a {hasta}")

    def _etiqueta_auto(self) -> str:
        if self.desde.day == 1 and self.hasta == _fin_de_mes(self.hasta):
            a, b = etiqueta_mes(self.desde), etiqueta_mes(self.hasta)
            return a if a == b else f"{a} a {b}"
        return f"{self.desde:%d-%m-%Y} a {self.hasta:%d-%m-%Y}"

    # --- constructores (métodos de clase) ---------------------------------------------------
    @classmethod
    def del_anio(cls, anio: int) -> "Periodo":
        return cls(date(anio, 1, 1), date(anio, 12, 31), f"año {anio}")

    @classmethod
    def del_semestre(cls, anio: int, s: int) -> "Periodo":
        if s not in (1, 2):
            raise ErrorTDA("El semestre debe ser 1 o 2")
        return cls(date(anio, 1 if s == 1 else 7, 1), date(anio, 6, 30) if s == 1 else date(anio, 12, 31),
                   f"{'primer' if s == 1 else 'segundo'} semestre {anio}")

    @classmethod
    def del_trimestre(cls, anio: int, t: int) -> "Periodo":
        if t not in (1, 2, 3, 4):
            raise ErrorTDA("El trimestre debe estar entre 1 y 4")
        inicio = date(anio, 3 * (t - 1) + 1, 1)
        return cls(inicio, _fin_de_mes(date(anio, 3 * t, 1)), f"T{t}-{anio}")

    @classmethod
    def del_mes(cls, anio: int, mes: int) -> "Periodo":
        if not 1 <= mes <= 12:
            raise ErrorTDA("El mes debe estar entre 1 y 12")
        return cls(date(anio, mes, 1), _fin_de_mes(date(anio, mes, 1)), f"{MESES[mes - 1]} {anio}")

    @classmethod
    def ultimos_meses(cls, n: int, fecha_max: date) -> "Periodo":
        if n < 1:
            raise ErrorTDA("n debe ser >= 1")
        y, m = fecha_max.year, fecha_max.month - (n - 1)
        while m < 1:
            m += 12
            y -= 1
        desde = date(y, m, 1)
        return cls(desde, fecha_max, f"últimos {n} meses disponibles ({etiqueta_mes(desde)} a {etiqueta_mes(fecha_max)})"
                   if n > 1 else f"último mes disponible ({etiqueta_mes(fecha_max)})")

    # --- operaciones -------------------------------------------------------------------------
    def contiene(self, d: date) -> bool:
        return self.desde <= d <= self.hasta

    def se_solapa(self, otro: "Periodo") -> bool:
        return self.desde <= otro.hasta and otro.desde <= self.hasta

    def recortar(self, minimo: date, maximo: date) -> "Periodo | None":
        """Intersección con el rango disponible. None si no hay intersección."""
        d, h = max(self.desde, minimo), min(self.hasta, maximo)
        if d > h:
            return None
        if (d, h) == (self.desde, self.hasta):
            return self
        return Periodo(d, h, f"{self.etiqueta} (datos disponibles: {d:%d-%m-%Y} a {h:%d-%m-%Y})", self.explicito)

    def mismo_periodo_anio_anterior(self) -> "Periodo":
        try:
            d = self.desde.replace(year=self.desde.year - 1)
            h = self.hasta.replace(year=self.hasta.year - 1)
        except ValueError:  # 29-feb
            d = self.desde.replace(year=self.desde.year - 1, day=28)
            h = self.hasta.replace(year=self.hasta.year - 1, day=28)
        etiqueta = self.etiqueta
        if "últim" in etiqueta or "todo el rango" in etiqueta:
            etiqueta = ""            # se recalcula a partir de las fechas (p. ej. "abr-2025 a sep-2025")
        for anio in (self.desde.year, self.hasta.year):
            etiqueta = etiqueta.replace(str(anio), str(anio - 1))
        return Periodo(d, h, etiqueta, self.explicito)

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1

    def a_dict(self) -> dict:
        return {"desde": self.desde.isoformat(), "hasta": self.hasta.isoformat(), "etiqueta": self.etiqueta,
                "explicito": self.explicito}

    def __str__(self) -> str:
        return self.etiqueta


# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Filtro:
    """Restricción 'dimensión IN (valores)'. La dimensión debe existir en el catálogo."""
    dimension: str
    valores: tuple = field(default_factory=tuple)

    def __post_init__(self):
        from agente.catalogo import DIMENSIONES
        if self.dimension not in DIMENSIONES:
            raise ErrorTDA(f"Dimensión de filtro inexistente: {self.dimension}")
        vals = tuple(str(v).strip() for v in (self.valores or ()) if str(v).strip())
        if not vals:
            raise ErrorTDA("Un filtro debe tener al menos un valor")
        object.__setattr__(self, "valores", vals)

    def describir(self) -> str:
        from agente.catalogo import DIMENSIONES
        return f"{DIMENSIONES[self.dimension].nombre} = {' / '.join(self.valores)}"

    def a_dict(self) -> dict:
        return {"dimension": self.dimension, "valores": list(self.valores)}


# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ResultadoValidacion:
    """Resultado de aplicar una ReglaValidacion (valor, no tiene identidad propia)."""
    regla: str
    nombre: str
    aprobada: bool
    severidad: str          # bloqueante | advertencia | info
    mensaje: str
    momento: str = ""

    def a_dict(self) -> dict:
        return {"regla": self.regla, "nombre": self.nombre, "aprobada": self.aprobada,
                "severidad": self.severidad, "momento": self.momento, "mensaje": self.mensaje}
