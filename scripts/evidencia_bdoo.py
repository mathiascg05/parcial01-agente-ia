"""
Genera la EVIDENCIA DE LA BDOO (sección 8.4): una sesión completa almacenada en ZODB y su recorrido
objeto por objeto (IDO, clase, atributos y apuntadores), identidad compartida, LOB, versionamiento,
herencia/polimorfismo y una prueba de persistencia (cerrar y reabrir la base).

  python scripts/evidencia_bdoo.py            -> docs/evidencias/evidencia_bdoo.md y .json
"""
from __future__ import annotations

import json
from datetime import datetime
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.bdoo.repositorio import RepositorioBDOO  # noqa: E402
from agente.cli import crear_servicios  # noqa: E402

DESTINO = RAIZ / "docs" / "evidencias"
BDOO_EVIDENCIA = RAIZ / "data" / "bdoo_evidencia" / "evidencia.fs"

PREGUNTAS = [
    "¿Qué canal concentra el mayor valor de ventas en 2026?",
    "¿y en 2025?",
    "¿Cuál fue el mejor canal?",
    "¿Cuánto vendimos de Jardinería en 2025?",
    "Borra las ventas de enero de 2026",
]


def j(o):
    return json.dumps(o, ensure_ascii=False, indent=2, default=str)


def main():
    if BDOO_EVIDENCIA.parent.exists():
        shutil.rmtree(BDOO_EVIDENCIA.parent)
    repo = RepositorioBDOO(BDOO_EVIDENCIA)
    repo.inicializar()
    serv = crear_servicios("reglas", narrativa_llm=False)

    # 1) Sesión completa (5 preguntas: respuesta, seguimiento, aclaración, sin datos, rechazo)
    codigo = repo.ejecutar(lambda root: RepositorioBDOO.nueva_sesion(root, "V-12345678", "Evidencia BDOO").codigo)
    for q in PREGUNTAS:
        repo.ejecutar(lambda root, q=q: root["agente"].responder(root["sesiones"][codigo], q, serv))
    repo.ejecutar(lambda root: root["sesiones"][codigo].cerrar())

    # 2) Versionamiento: nueva versión de una consulta del catálogo (historial explícito + historial de ZODB)
    def versionar(root):
        c = root["agente"].consulta("CQ-02")
        c.nueva_version("Se agrega desempate por nombre de miembro en el ORDER BY")
        return c.ido
    oid_cq02 = repo.ejecutar(versionar)
    repo.cerrar()

    # 3) Persistencia real: se REABRE la base desde disco y se recorre el grafo de objetos
    repo = RepositorioBDOO(BDOO_EVIDENCIA)
    md = ["# Evidencia de la BDOO (ZODB)", "",
          f"Archivo: `{BDOO_EVIDENCIA.relative_to(RAIZ)}` (FileStorage) · blobs (LOB): "
          f"`{BDOO_EVIDENCIA.parent.relative_to(RAIZ)}/evidencia_blobs/`", "",
          "La base se cerró y se volvió a abrir antes de generar este documento: todo lo que sigue fue leído "
          "desde disco (persistencia real, no memoria del proceso).", ""]
    evidencia = {}

    def recorrer(root):
        s = root["sesiones"][codigo]
        agente = root["agente"]
        md.append("## 1. Raíz de la base y objetos de configuración")
        md.append(f"- `root['agente']` → **{agente.clase}** IDO `{agente.ido}`: {agente.describir()}")
        md.append(f"- `root['usuarios']` → OOBTree con {len(root['usuarios'])} usuarios; `root['sesiones']` → OOBTree "
                  f"con {len(root['sesiones'])} sesión(es); `root['fuentes']` → {len(root['fuentes'])} FuenteDato")
        md.append("")
        md.append("| Objeto | Clase (herencia) | IDO |")
        md.append("|---|---|---|")
        for c in agente.catalogo:
            md.append(f"| {c.codigo} {c.nombre} | {c.clase} → ConsultaAnalitica → ObjetoAgente | `{c.ido}` |")
        for r in agente.reglas:
            md.append(f"| {r.codigo} {r.nombre} | {r.clase} → ReglaValidacion → ObjetoAgente | `{r.ido}` |")
        for u in root["usuarios"].values():
            md.append(f"| Usuario {u.nombre} | {u.clase} → Usuario → ObjetoAgente | `{u.ido}` |")
        md.append("")

        md.append("## 2. Sesión completa: pregunta → intención → consulta → resultado → respuesta")
        md.append(f"**Sesion** `{s.codigo}` · IDO `{s.ido}` · usuario → IDO `{s.usuario.ido}` ({s.usuario.describir()}) · "
                  f"resumen {s.resumen()}")
        md.append("")
        evidencia["sesion"] = s.a_dict()
        evidencia["preguntas"] = []
        for n, p in enumerate(s.preguntas, 1):
            r = p.respuesta
            bloque = {"pregunta": p.a_dict(), "intencion": p.intencion.a_dict() if p.intencion else None,
                      "respuesta": r.a_dict()}
            md.append(f"### 2.{n} «{p.texto}»  → estado **{p.estado}**")
            md.append(f"- **Pregunta** IDO `{p.ido}` · historial de estados: "
                      + " → ".join(e[0] for e in p.a_dict()["historial_estados"]))
            if p.intencion:
                md.append(f"- **Intencion** IDO `{p.intencion.ido}` · origen {p.intencion.origen} · {p.intencion.describir()}")
            if r.resultado is not None:
                res = r.resultado
                bloque["resultado"] = res.a_dict()
                bloque["consulta"] = res.consulta.a_dict()
                md.append(f"- **ConsultaAnalitica** (apuntador) IDO `{res.consulta.ido}` · {res.consulta.describir()}")
                md.append(f"- **ResultadoConsulta** IDO `{res.ido}` · {res.describir()} · LOB CSV de "
                          f"{len(res.leer_csv().encode())} bytes")
                md.append("```sql\n" + res.sql + "\n```")
                md.append(f"Parámetros: `{res.parametros}`")
            md.append(f"- **RespuestaAgente** IDO `{r.ido}` · tipo **{r.tipo}**")
            md.append(f"  > {r.resumen.replace('**', '')}")
            if r.fuentes:
                md.append("- **FuenteDato** (apuntadores): " + ", ".join(f"`{f.tabla}` IDO `{f.ido}`" for f in r.fuentes))
            if r.advertencias:
                md.append("- Advertencias: " + " | ".join(r.advertencias))
            md.append("- Reglas aplicadas: " + ", ".join(f"{v['regla']}{'✔' if v['aprobada'] else '✘'}" for v in r.validaciones))
            md.append("")
            evidencia["preguntas"].append(bloque)

        md.append("## 3. Identidad de objeto y objetos compartidos")
        r1, r2 = s.preguntas[0].respuesta, s.preguntas[1].respuesta
        f1 = {f.tabla: f for f in r1.fuentes}
        f2 = {f.tabla: f for f in r2.fuentes}
        md.append("Las respuestas 2.1 y 2.2 apuntan al **mismo objeto** FuenteDato `dm.fact_ventas` (misma identidad, no una copia):")
        md.append(f"- `r1.fuentes['dm.fact_ventas'] is r2.fuentes['dm.fact_ventas']` → **{f1['dm.fact_ventas'] is f2['dm.fact_ventas']}** "
                  f"· IDO `{f1['dm.fact_ventas'].ido}` · usos registrados: {f1['dm.fact_ventas'].usos}")
        md.append(f"- Ambos resultados apuntan a la misma ConsultaAnalitica: "
                  f"**{r1.resultado.consulta is r2.resultado.consulta}** (IDO `{r1.resultado.consulta.ido}`)")
        md.append(f"- Memoria operativa: `sesion.contexto()['ultima_intencion']` es la Intencion IDO "
                  f"`{s.contexto()['ultima_intencion'].ido}` (la de la pregunta 2.2, que reutilizó la 2.1).")
        md.append("")

        md.append("## 4. LOB (Blob) asociado a un ResultadoConsulta")
        md.append("```csv\n" + r1.resultado.leer_csv().strip() + "\n```")
        md.append("")

        md.append("## 5. Encapsulamiento, TDA y polimorfismo")
        u = s.usuario
        md.append(f"- TDA `DocumentoIdentidad.formato('V-12345678')` → `{u.documento}` (tipo {u.documento.tipo}); "
                  "un valor inválido lanza ErrorTDA (ver tests).")
        md.append(f"- Polimorfismo de Usuario: `Gerente.nivel_detalle()` = `{u.nivel_detalle()}`, muestra SQL = {u.muestra_sql()}; "
                  f"`Analista.nivel_detalle()` = `{root['usuarios']['V-23456789'].nivel_detalle()}`, muestra SQL = "
                  f"{root['usuarios']['V-23456789'].muestra_sql()}.")
        md.append("- Polimorfismo de ConsultaAnalitica: el agente envía el mismo mensaje `aplica_a(intencion)` a cada consulta "
                  "del catálogo y `construir_sql(intencion)` a la elegida; cada subclase responde distinto.")
        md.append("- Polimorfismo de ReglaValidacion: `aplicar(ctx)` (método plantilla) → `validar(ctx)` específico de cada regla. "
                  "Estadísticas persistidas: " + ", ".join(f"{r.codigo}: {r.evaluaciones} eval./{r.fallos} fallos" for r in agente.reglas))
        md.append("")
        c = agente.consulta("CQ-02")
        md.append("## 6. Versionamiento")
        md.append(f"- Versionamiento explícito de `{c.codigo}` (IDO `{c.ido}`): versión actual **v{c.version}**")
        for v in c.historial_versiones:
            md.append(f"  - v{v[0]} · {v[1]} · {v[2]}")
        return c

    repo.ejecutar(recorrer)
    hist = repo.db.history(bytes.fromhex(oid_cq02), size=10)
    md.append("- Historial interno de ZODB para el mismo OID: cada transacción que modificó el objeto (cada ejecución "
              "incrementa su contador y la última agregó la v2) dejó una revisión recuperable:")
    md.append("")
    md.append("| tid | fecha | tamaño |")
    md.append("|---|---|---|")
    for h in hist:
        md.append(f"| `{h['tid'].hex()}` | {datetime.fromtimestamp(h['time']):%Y-%m-%d %H:%M:%S.%f} | {h['size']} bytes |")
    md.append("")
    md.append("## 7. Transacciones y recuperación")
    md.append("Cada pregunta se procesó dentro de una transacción ZODB (`RepositorioBDOO.transaccion()`): si algo falla "
              "se hace `abort()` y no queda ningún objeto a medio guardar; ante un `ConflictError` (dos procesos "
              "modificando el mismo objeto) se reintenta. FileStorage es un log de sólo-anexión, lo que permite "
              "recuperar versiones anteriores.")
    repo.cerrar()
    serv.datamart.cerrar()

    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "evidencia_bdoo.md").write_text("\n".join(md), encoding="utf-8")
    (DESTINO / "evidencia_bdoo.json").write_text(j(evidencia), encoding="utf-8")
    print("\n".join(md[:60]))
    print(f"\n... -> {DESTINO.relative_to(RAIZ)}/evidencia_bdoo.md / .json")


if __name__ == "__main__":
    main()
