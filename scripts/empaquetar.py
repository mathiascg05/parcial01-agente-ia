"""
Arma la entrega para Canvas con la convención de nombres del enunciado (sección 9).

  python scripts/empaquetar.py --equipo 07

Genera en entregables/:
  Equipo07_Datamart.sql, Equipo07_AgenteIA.zip (código sin credenciales) y Equipo07_Parcial01.zip con los 6 archivos.
Antes regenera los documentos con el número de equipo (informe, bitácora, pruebas, defensa) si se pasa --regenerar.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXCLUIR = ("entregables/", "data/bdoo/", "data/bdoo_evidencia/", ".venv/", "__pycache__", ".pytest_cache")


def archivos_codigo() -> list[str]:
    salida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.split()
    return [f for f in salida if Path(f).name != ".env" and not any(f.startswith(e) or e in f for e in EXCLUIR)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--equipo", required=True)
    ap.add_argument("--regenerar", action="store_true", help="regenera pruebas, informe, bitácora y defensa con el número de equipo")
    a = ap.parse_args()
    eq = a.equipo
    ent = RAIZ / "entregables"
    ent.mkdir(exist_ok=True)
    py = sys.executable
    if a.regenerar:
        subprocess.run([py, "scripts/ejecutar_pruebas.py", "--equipo", eq], cwd=RAIZ, check=True)
        subprocess.run([py, "docs/informe/build_informe.py", "--equipo", eq], cwd=RAIZ, check=True)
        subprocess.run([py, "docs/informe/build_bitacora.py", "--equipo", eq], cwd=RAIZ, check=True)
        if os.environ.get("PPTX_SKILL") or (RAIZ / "node_modules").exists():
            subprocess.run(["node", "docs/defensa/build_defensa.js", eq], cwd=RAIZ, check=True)
    shutil.copy(RAIZ / "sql" / "Datamart.sql", ent / f"Equipo{eq}_Datamart.sql")
    zcod = ent / f"Equipo{eq}_AgenteIA.zip"
    with zipfile.ZipFile(zcod, "w", zipfile.ZIP_DEFLATED) as z:
        for f in archivos_codigo():
            z.write(RAIZ / f, f"Equipo{eq}_AgenteIA/{f}")
    finales = [f"Equipo{eq}_Informe_Parcial01.pdf", f"Equipo{eq}_Datamart.sql", f"Equipo{eq}_AgenteIA.zip",
               f"Equipo{eq}_Pruebas.xlsx", f"Equipo{eq}_BitacoraIA.pdf", f"Equipo{eq}_Defensa.pptx"]
    faltan = [f for f in finales if not (ent / f).exists()]
    if faltan:
        sys.exit(f"Faltan archivos (use --regenerar o genérelos): {faltan}")
    ztot = ent / f"Equipo{eq}_Parcial01.zip"
    with zipfile.ZipFile(ztot, "w", zipfile.ZIP_DEFLATED) as z:
        for f in finales:
            z.write(ent / f, f)
    for f in finales + [ztot.name]:
        print(f"  {f:40} {(ent / f).stat().st_size / 1024:8.0f} KB")
    print(f"-> {ztot.relative_to(RAIZ)}  (cargar en Canvas · Módulo 07)")


if __name__ == "__main__":
    main()
