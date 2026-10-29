"""
Mecanismo de persistencia: ZODB (Zope Object Database), base de datos orientada a objetos nativa
de Python.

  - FileStorage (archivo agente.fs) guarda los objetos serializados, cada uno con su OID.
  - blob_dir guarda los objetos grandes (LOB) de forma separada.
  - Raíz (root): punto de entrada por nombre; desde ahí todo se alcanza navegando referencias
    (persistencia por alcanzabilidad: no hay que "insertar" cada objeto).
  - OOBTree: índices ordenados (B-Trees) para sesiones y usuarios.
  - Transacciones ACID con control de concurrencia optimista (ConflictError -> reintento).
"""
from __future__ import annotations

import contextlib
from datetime import datetime

import transaction
import ZODB
from BTrees.OOBTree import OOBTree
from persistent.mapping import PersistentMapping
from ZODB.FileStorage import FileStorage
from ZODB.POSException import ConflictError
from zc.lockfile import LockError

from agente.bdoo.agente_analitico import AgenteAnalitico
from agente.bdoo.consultas import crear_catalogo
from agente.bdoo.modelo import Analista, FuenteDato, Gerente, Sesion
from agente.bdoo.reglas import crear_reglas
from agente.catalogo import FUENTES
from agente.config import CONFIG


class RepositorioBDOO:
    def __init__(self, ruta=None, blobs=None):
        from pathlib import Path
        ruta = Path(ruta) if ruta else CONFIG.zodb_path
        blobs = Path(blobs) if blobs else (ruta.parent / f"{ruta.stem}_blobs" if ruta != CONFIG.zodb_path else CONFIG.zodb_blobs)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        blobs.mkdir(parents=True, exist_ok=True)
        self.ruta = ruta
        try:
            self.storage = FileStorage(str(ruta), blob_dir=str(blobs))
        except LockError as e:
            raise RuntimeError(f"La BDOO {ruta} está abierta por otro proceso (p. ej. la app Streamlit). FileStorage "
                               f"admite un solo proceso: ciérrelo o use otro archivo con ZODB_PATH / --bdoo.") from e
        self.db = ZODB.DB(self.storage)

    def cerrar(self):
        self.db.close()

    @contextlib.contextmanager
    def transaccion(self, intentos: int = 3):
        """Abre una conexión con su propio gestor de transacciones; confirma al salir.
        Ante un conflicto de concurrencia (ConflictError) se aborta y se propaga para reintentar."""
        tm = transaction.TransactionManager()
        conn = self.db.open(tm)
        try:
            yield conn.root()
            tm.commit()
        except Exception:
            tm.abort()
            raise
        finally:
            conn.close()

    def ejecutar(self, funcion, intentos: int = 3):
        """Ejecuta funcion(root) dentro de una transacción, reintentando ante conflictos."""
        for i in range(intentos):
            try:
                with self.transaccion() as root:
                    return funcion(root)
            except ConflictError:
                if i == intentos - 1:
                    raise

    # ------------------------------------------------------------------------------------------
    def inicializar(self, reiniciar: bool = False) -> bool:
        """Crea los objetos raíz si no existen. Devuelve True si los creó."""
        def crear(root):
            if "agente" in root and not reiniciar:
                return False
            sistema = "PostgreSQL · Data Mart de Ventas (esquema dm)"
            fuentes = PersistentMapping({f.tabla: FuenteDato(sistema, f.tabla, f.tipo, f.campos, f.descripcion)
                                         for f in FUENTES})
            root["fuentes"] = fuentes
            root["agente"] = AgenteAnalitico("Agente Analítico de Ventas", crear_catalogo(fuentes), crear_reglas(),
                                             fuentes)
            root["usuarios"] = OOBTree()
            root["sesiones"] = OOBTree()
            for u in (Gerente("Gerencia General", "V-12345678", "gerencia@avila.example"),
                      Analista("Analista de Datos", "V-23456789", "analitica@avila.example")):
                root["usuarios"][str(u.documento)] = u
            root["meta"] = PersistentMapping({"creado": datetime.now().isoformat(timespec="seconds"),
                                              "esquema": "1.0"})
            return True
        return self.ejecutar(crear)

    @staticmethod
    def asignar_oids(root) -> None:
        """Savepoint: la BDOO asigna IDO a los objetos nuevos antes del commit (útil para mostrarlos)."""
        root._p_jar.transaction_manager.savepoint(True)

    @staticmethod
    def nueva_sesion(root, documento_usuario: str, titulo: str = "") -> Sesion:
        usuario = root["usuarios"][documento_usuario]
        codigo = f"S-{datetime.now():%Y%m%d-%H%M%S-%f}"[:-3]
        s = Sesion(codigo, usuario, titulo)
        root["sesiones"][codigo] = s
        return s
