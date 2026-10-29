"""
Acceso al Data Mart (PostgreSQL) con el rol de SOLO LECTURA `agente_lector`.

Controles de defensa en profundidad:
  1. Las consultas se construyen desde el catálogo (listas blancas) y los valores van parametrizados.
  2. La regla RV07 inspecciona el SQL antes de ejecutarlo (sólo SELECT, sólo tablas dm.*).
  3. La conexión abre transacciones READ ONLY y con statement_timeout.
  4. El rol de base de datos sólo tiene SELECT sobre el esquema dm (ver §6 del script SQL).
"""
from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import psycopg

from agente.catalogo import DIMENSIONES, DIMENSIONES_FILTRABLES
from agente.config import CONFIG


def normalizar(texto: str) -> str:
    """minúsculas y sin acentos (para comparar texto del usuario con valores del Data Mart)."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return " ".join(t.lower().replace("-", " ").split())


@dataclass
class MetadatosDataMart:
    """Lo que el agente sabe del Data Mart: rango de fechas y valores válidos por dimensión."""
    fecha_min: date
    fecha_max: date
    valores: dict = field(default_factory=dict)    # dimension -> [valores canónicos]

    def resolver_valor(self, dimension: str, texto: str) -> str | None:
        """Devuelve el valor canónico (con mayúsculas/acentos) que coincide con el texto, o None."""
        objetivo = normalizar(texto)
        for v in self.valores.get(dimension, []):
            if normalizar(v) == objetivo:
                return v
        return None

    def opciones(self, dimension: str, n: int = 12) -> list[str]:
        """Valores 'reales' de una dimensión (sin miembros especiales No informado / Sin correspondencia)."""
        especiales = ("no informad", "sin correspondencia", "consumidor final")
        return [v for v in self.valores.get(dimension, []) if not any(e in normalizar(v) for e in especiales)][:n]

    def sugerencias(self, dimension: str, texto: str, n: int = 5) -> list[str]:
        import difflib
        mapa = {normalizar(v): v for v in self.valores.get(dimension, [])}
        return [mapa[k] for k in difflib.get_close_matches(normalizar(texto), list(mapa), n=n, cutoff=0.5)]


class ErrorDataMart(RuntimeError):
    pass


class DataMart:
    """Fachada de acceso a datos (patrón Facade). Una conexión de solo lectura por instancia."""

    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or CONFIG.dsn()
        self._conn: psycopg.Connection | None = None
        self._meta: MetadatosDataMart | None = None

    # -- conexión --------------------------------------------------------------------------------
    def _conexion(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._dsn, autocommit=False, connect_timeout=8)
            self._conn.read_only = True
        return self._conn

    def cerrar(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    @property
    def descripcion(self) -> str:
        partes = dict(p.split("=", 1) for p in self._dsn.split() if "=" in p and not p.startswith("password"))
        return f"PostgreSQL {partes.get('host')}:{partes.get('port')}/{partes.get('dbname')} (rol {partes.get('user')})"

    # -- ejecución -------------------------------------------------------------------------------
    def ejecutar(self, sql: str, params: dict | None = None) -> tuple[list[str], list[tuple], float]:
        """Ejecuta una consulta de lectura. Devuelve (columnas, filas, duración_ms)."""
        conn = self._conexion()
        t0 = time.perf_counter()
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute(sql, params or {})
                columnas = [d.name for d in cur.description] if cur.description else []
                filas = [tuple(_a_python(v) for v in fila) for fila in cur.fetchall()] if cur.description else []
            conn.rollback()   # transacción de solo lectura: nunca se confirma nada
        except psycopg.Error as e:
            conn.rollback()
            raise ErrorDataMart(f"{type(e).__name__}: {str(e).strip().splitlines()[0]}") from e
        return columnas, filas, (time.perf_counter() - t0) * 1000

    # -- metadatos -------------------------------------------------------------------------------
    def metadatos(self, refrescar: bool = False) -> MetadatosDataMart:
        if self._meta is None or refrescar:
            _, filas, _ = self.ejecutar(
                "SELECT MIN(f.fecha), MAX(f.fecha) FROM dm.fact_ventas v JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk")
            fmin, fmax = filas[0]
            valores = {}
            for cod in DIMENSIONES_FILTRABLES:
                d = DIMENSIONES[cod]
                sql = f"SELECT DISTINCT {d.expresion} FROM {d.tabla} {d.alias} ORDER BY 1"   # lista blanca
                _, filas, _ = self.ejecutar(sql)
                valores[cod] = [f[0] for f in filas if f[0] is not None]
            self._meta = MetadatosDataMart(fmin, fmax, valores)
        return self._meta


def _a_python(v):
    if isinstance(v, Decimal):
        return float(v) if v != v.to_integral_value() else (int(v) if abs(v) < 10**15 else float(v))
    return v
