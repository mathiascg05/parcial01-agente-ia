"""
Interfaz de línea de comandos del agente.

  python -m agente.cli                         # conversación interactiva
  python -m agente.cli -p "¿Cuál fue el ingreso neto por mes?"
  python -m agente.cli --modo reglas --usuario V-23456789 -p "..."
"""
from __future__ import annotations

import argparse
import json
import sys

from agente.bdoo.agente_analitico import ServiciosAgente
from agente.bdoo.repositorio import RepositorioBDOO
from agente.config import CONFIG
from agente.datamart import DataMart
from agente.interpretes import crear_interprete
from agente.interpretes.llm import InterpreteHibrido, InterpreteLLM
from agente.redactor import presentar


def crear_servicios(modo: str | None = None, narrativa_llm: bool = True) -> ServiciosAgente:
    interprete = crear_interprete(modo)
    narrador = None
    if narrativa_llm:
        if isinstance(interprete, InterpreteHibrido):
            narrador = interprete.llm
        elif isinstance(interprete, InterpreteLLM):
            narrador = interprete
    return ServiciosAgente(DataMart(), interprete, narrador)


def preguntar(repo: RepositorioBDOO, servicios: ServiciosAgente, codigo_sesion: str, texto: str) -> dict:
    def hacer(root):
        sesion = root["sesiones"][codigo_sesion]
        p = root["agente"].responder(sesion, texto, servicios)
        RepositorioBDOO.asignar_oids(root)
        return {"markdown": presentar(p.respuesta, sesion.usuario), "pregunta": p.a_dict(),
                "intencion": p.intencion.a_dict() if p.intencion else None, "respuesta": p.respuesta.a_dict()}
    return repo.ejecutar(hacer)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Agente analítico de ventas")
    ap.add_argument("-p", "--pregunta", help="pregunta única (si se omite, modo interactivo)")
    ap.add_argument("--modo", default=None, choices=["auto", "llm", "reglas"], help="intérprete")
    ap.add_argument("--usuario", default="V-23456789", help="documento del usuario (V-12345678 gerente, V-23456789 analista)")
    ap.add_argument("--json", action="store_true", help="muestra la traza completa en JSON")
    a = ap.parse_args(argv)

    repo = RepositorioBDOO()
    repo.inicializar()
    servicios = crear_servicios(a.modo)
    codigo = repo.ejecutar(lambda root: RepositorioBDOO.nueva_sesion(root, a.usuario, "CLI").codigo)
    print(f"Sesión {codigo} · intérprete: {servicios.interprete.nombre} · LLM: "
          f"{'sí (' + CONFIG.openrouter_model + ')' if CONFIG.llm_disponible else 'no (reglas)'}\n")

    def ciclo(texto):
        out = preguntar(repo, servicios, codigo, texto)
        print(out["markdown"])
        if a.json:
            print(json.dumps({k: out[k] for k in ("intencion", "respuesta")}, ensure_ascii=False, indent=2, default=str))
        print(f"\n[IDO pregunta {out['pregunta']['ido']} · estado {out['pregunta']['estado']}]\n")

    try:
        if a.pregunta:
            ciclo(a.pregunta)
        else:
            print("Escriba su pregunta (vacío para salir).")
            for linea in sys.stdin if not sys.stdin.isatty() else iter(lambda: input("> "), ""):
                linea = linea.strip()
                if not linea:
                    break
                ciclo(linea)
    finally:
        repo.ejecutar(lambda root: root["sesiones"][codigo].cerrar())
        servicios.datamart.cerrar()
        repo.cerrar()


if __name__ == "__main__":
    main()
