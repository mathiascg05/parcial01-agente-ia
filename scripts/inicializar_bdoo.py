"""
Crea (o reinicia con --reiniciar) la BDOO del agente: AgenteAnalitico, catálogo de consultas, reglas,
fuentes y usuarios de demostración.     python scripts/inicializar_bdoo.py [--reiniciar]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente.bdoo.repositorio import RepositorioBDOO  # noqa: E402
from agente.config import CONFIG  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--reiniciar", action="store_true", help="borra la BDOO existente (sesiones incluidas)")
a = ap.parse_args()
if a.reiniciar:
    for p in (CONFIG.zodb_path.parent,):
        shutil.rmtree(p, ignore_errors=True)
repo = RepositorioBDOO()
creado = repo.inicializar()


def resumen(root):
    ag = root["agente"]
    print(f"{'Creada' if creado else 'Ya existía'}: {CONFIG.zodb_path}")
    print(f"  {ag.describir()} · IDO {ag.ido}")
    for c in ag.catalogo:
        print(f"  consulta {c.describir()} · {c.clase} · IDO {c.ido}")
    for r in ag.reglas:
        print(f"  regla    {r.describir()} · IDO {r.ido}")
    for u in root["usuarios"].values():
        print(f"  usuario  {u.describir()} · IDO {u.ido}")
    print(f"  sesiones almacenadas: {len(root['sesiones'])}")


repo.ejecutar(resumen)
repo.cerrar()
