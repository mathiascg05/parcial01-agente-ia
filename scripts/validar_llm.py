"""
Validación del intérprete LLM con respuestas REALES grabadas de OpenRouter.

Las respuestas de gpt-4o-mini (docs/evidencias/llm_openrouter/*.json) se obtuvieron el 29-10-2026 en el chat de
OpenRouter con el MISMO prompt de sistema del agente (agente/interpretes/llm.py). Este script las reproduce sin
red ni API key, y mide tres modos sobre las mismas preguntas:

  reglas   intérprete determinista (sin LLM)
  llm      la salida del LLM tal cual (sólo con las validaciones RV02–RV11 del agente)
  hibrido  la salida del LLM contrastada con la lectura literal (anclaje) — el modo por defecto del agente

  python scripts/validar_llm.py            -> docs/evidencias/validacion_llm.md y .json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import ejecutar_pruebas as ep  # noqa: E402
from agente.bdoo.agente_analitico import ServiciosAgente  # noqa: E402
from agente.bdoo.repositorio import RepositorioBDOO  # noqa: E402
from agente.datamart import DataMart  # noqa: E402
from agente.interpretes.base import InterpreteBase  # noqa: E402
from agente.interpretes.llm import InterpreteHibrido  # noqa: E402
from agente.interpretes.reglas_nl import InterpreteReglas  # noqa: E402

CARPETA = RAIZ / "docs" / "evidencias" / "llm_openrouter"


class LLMGrabado(InterpreteBase):
    """Devuelve la respuesta real que dio el LLM para cada pregunta (reproducción sin red)."""
    nombre = "llm-grabado"

    def __init__(self, por_texto: dict[str, dict]):
        self.por_texto = por_texto

    def interpretar(self, texto, meta, contexto=None):
        return dict(self.por_texto[texto])


def interpretes(por_texto):
    h = InterpreteHibrido()
    h.llm = LLMGrabado(por_texto)
    return {"reglas": InterpreteReglas(), "llm": LLMGrabado(por_texto), "hibrido": h}


def responder(repo, servicios, codigo, texto, interprete):
    if hasattr(interprete, "ultimos_ajustes"):
        interprete.ultimos_ajustes = []  # si RV01 rechaza antes de interpretar, no deben verse ajustes previos

    def hacer(root):
        p = root["agente"].responder(root["sesiones"][codigo], texto, servicios)
        RepositorioBDOO.asignar_oids(root)
        r, i = p.respuesta, p.intencion
        res = r.resultado
        return {"tipo": r.tipo, "resumen": r.resumen, "advertencias": r.advertencias, "validaciones": r.validaciones,
                "opciones": r.opciones, "columnas": res.columnas if res else [], "filas": res.filas if res else [],
                "intencion": i, "intencion_txt": i.describir() if i else "",
                "metrica": getattr(i, "metrica", None), "dimension": getattr(i, "dimension", None),
                "operacion": getattr(i, "operacion", None), "orden": getattr(i, "orden", None),
                "limite": getattr(i, "limite", None), "periodo": str(getattr(i, "periodo", "") or ""),
                "filtros": {f.dimension: list(f.valores) for f in getattr(i, "filtros", ())},
                "ajustes": list(getattr(interprete, "ultimos_ajustes", []) or [])}
    return repo.ejecutar(hacer)


def cumple(o: dict, esperado: dict) -> tuple[bool, list[str]]:
    fallas = []
    for k, v in esperado.items():
        if k == "respuesta":
            ok = o["tipo"] in (v if isinstance(v, list) else [v])
        elif k == "periodo":
            ok = v in o["periodo"]
        elif k == "filtros":
            ok = all(sorted(o["filtros"].get(d, [])) == sorted(vals) for d, vals in v.items())
        elif isinstance(v, list):
            ok = o.get(k) in v
        else:
            ok = o.get(k) == v
        if not ok:
            fallas.append(f"{k}: esperado {v}, obtenido {o.get('tipo') if k == 'respuesta' else o.get(k)}")
    if o["tipo"] != "RESPUESTA" and esperado.get("respuesta") in ("RESPUESTA", ["RESPUESTA"]):
        fallas = [f"respuesta: {o['tipo']} — {o['resumen'][:90]}"]
    return not fallas, fallas


def main():
    dm = DataMart()
    tmp = tempfile.mkdtemp()
    repo = RepositorioBDOO(Path(tmp) / "validacion_llm.fs")
    repo.inicializar()
    casos = [c for c in ep.construir_casos(ep.modelo_independiente()) if not c.get("previa")]
    informe = {"conjuntos": []}

    # --- 1. Matriz oficial de pruebas (mismas verificaciones contra el oráculo pandas) -------------------------
    for archivo in ("matriz_prompt_v1.json", "matriz_prompt_v2.json"):
        d = json.loads((CARPETA / archivo).read_text(encoding="utf-8"))
        grab = d["respuestas_llm"]
        sel = [c for c in casos if c["id"] in grab]
        modos = interpretes({c["pregunta"]: grab[c["id"]] for c in sel})
        filas = []
        for c in sel:
            fila = {"id": c["id"], "pregunta": c["pregunta"], "llm_crudo": grab[c["id"]]}
            for m, it in modos.items():
                servicios = ServiciosAgente(dm, it, None)
                cod = repo.ejecutar(lambda r: RepositorioBDOO.nueva_sesion(r, "V-23456789", f"val {m}").codigo)
                o = responder(repo, servicios, cod, c["pregunta"], it)
                try:
                    ok = bool(c["verificar"](o))
                except Exception:  # noqa: BLE001  (p. ej. el modo devolvió otra métrica y no hay esa columna)
                    ok = False
                fila[m] = {"ok": ok, "tipo": o["tipo"], "intencion": o["intencion_txt"], "resumen": o["resumen"][:200],
                           "ajustes": o["ajustes"]}
            filas.append(fila)
        informe["conjuntos"].append({"nombre": f"Matriz de pruebas · prompt {d['prompt']}", "archivo": archivo,
                                     "nota": d.get("nota", ""), "criterio": "verificación de la matriz (oráculo pandas)",
                                     "filas": filas})

    # --- 2. Preguntas nuevas (fuera de la matriz) con interpretación esperada --------------------------------
    for archivo in ("exploratorio_1.json", "exploratorio_2.json"):
        d = json.loads((CARPETA / archivo).read_text(encoding="utf-8"))
        grab = d["respuestas_llm"]
        modos = interpretes({v["pregunta"]: grab[k] for k, v in d["preguntas"].items()})
        filas = []
        for k, v in d["preguntas"].items():
            fila = {"id": k, "pregunta": v["pregunta"], "esperado": v["esperado"], "llm_crudo": grab[k]}
            for m, it in modos.items():
                servicios = ServiciosAgente(dm, it, None)
                cod = repo.ejecutar(lambda r: RepositorioBDOO.nueva_sesion(r, "V-23456789", f"val {m}").codigo)
                o = responder(repo, servicios, cod, v["pregunta"], it)
                ok, fallas = cumple(o, v["esperado"])
                fila[m] = {"ok": ok, "tipo": o["tipo"], "intencion": o["intencion_txt"], "resumen": o["resumen"][:200],
                           "fallas": fallas, "ajustes": o["ajustes"]}
            filas.append(fila)
        informe["conjuntos"].append({"nombre": f"Preguntas nuevas · {archivo.removesuffix('.json')}", "archivo": archivo,
                                     "nota": d.get("nota", ""), "criterio": "interpretación esperada (campos clave)",
                                     "filas": filas})
    repo.cerrar()
    dm.cerrar()

    # --- salida -------------------------------------------------------------------------------------------------
    lineas = ["# Validación del intérprete LLM con respuestas reales de OpenRouter", "",
              "Modelo `openai/gpt-4o-mini` vía OpenRouter, 29-10-2026, con el prompt de sistema del agente. "
              "Las respuestas reales están grabadas en `docs/evidencias/llm_openrouter/` y se reproducen sin red "
              "con `python scripts/validar_llm.py`.", "",
              "| Conjunto | Preguntas | Reglas | LLM solo | Híbrido (LLM + anclaje) |", "|---|---|---|---|---|"]
    for cj in informe["conjuntos"]:
        n = len(cj["filas"])
        tot = {m: sum(f[m]["ok"] for f in cj["filas"]) for m in ("reglas", "llm", "hibrido")}
        cj["totales"] = tot
        lineas.append(f"| {cj['nombre']} | {n} | {tot['reglas']}/{n} | {tot['llm']}/{n} | {tot['hibrido']}/{n} |")
    for cj in informe["conjuntos"]:
        lineas += ["", f"## {cj['nombre']}", "", f"Criterio: {cj['criterio']}. {cj['nota']}".strip(), "",
                   "| Id | Pregunta | Reglas | LLM solo | Híbrido | Ajustes del anclaje |", "|---|---|---|---|---|---|"]
        for f in cj["filas"]:
            marca = {m: ("✔" if f[m]["ok"] else "✘") + f" {f[m]['tipo']}" for m in ("reglas", "llm", "hibrido")}
            aj = "; ".join(f["hibrido"]["ajustes"]).replace("|", "/") or "—"
            lineas.append(f"| {f['id']} | {f['pregunta']} | {marca['reglas']} | {marca['llm']} | {marca['hibrido']} | {aj} |")
    salida = RAIZ / "docs" / "evidencias"
    (salida / "validacion_llm.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    (salida / "validacion_llm.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str),
                                               encoding="utf-8")
    for cj in informe["conjuntos"]:
        n = len(cj["filas"])
        t = cj["totales"]
        print(f"{cj['nombre']:45} reglas {t['reglas']:>2}/{n}   llm {t['llm']:>2}/{n}   híbrido {t['hibrido']:>2}/{n}")
    print("-> docs/evidencias/validacion_llm.md")


if __name__ == "__main__":
    main()
