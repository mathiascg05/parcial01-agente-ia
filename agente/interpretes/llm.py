"""
Intérprete con LLM vía OpenRouter (API compatible con OpenAI).

El LLM SÓLO traduce la pregunta a un JSON con códigos del catálogo. No ve la base de datos, no
escribe SQL y su salida es tratada como dato no confiable: se valida con construir_intencion() y con
las reglas RV02–RV06. Si la llamada falla o el JSON es inválido, el intérprete híbrido usa las reglas.
"""
from __future__ import annotations

import json
import re
from datetime import date

from agente.catalogo import CRITERIOS_AMBIGUEDAD, DIMENSIONES, METRICAS
from agente.config import CONFIG
from agente.interpretes.base import ErrorInterpretacion, InterpreteBase, intencion_a_datos
from agente.interpretes.reglas_nl import InterpreteReglas


def _prompt_sistema(meta) -> str:
    metricas = "\n".join(f"- {m.codigo}: {m.nombre} ({m.regla})" for m in METRICAS.values())
    dims = "\n".join(f"- {d.codigo}: {d.nombre}" for d in DIMENSIONES.values())
    valores = "\n".join(f"- {k}: {', '.join(map(str, v[:40]))}" for k, v in meta.valores.items()
                        if k not in ("cliente", "producto"))
    return f"""Eres el módulo de interpretación de un agente analítico de ventas (Distribuidora Ávila C.A.).
Tu ÚNICA tarea es convertir la pregunta del usuario en un JSON. No respondas la pregunta, no inventes datos,
no escribas SQL.

Fecha de hoy: {date.today().isoformat()}. Datos disponibles en el Data Mart: desde {meta.fecha_min} hasta {meta.fecha_max}.
"Últimos N meses disponibles" se cuentan hacia atrás desde {meta.fecha_max}.

MÉTRICAS permitidas (usa sólo estos códigos):
{metricas}

DIMENSIONES permitidas (usa sólo estos códigos):
{dims}

VALORES conocidos por dimensión (para filtros; copia el valor exacto):
{valores}
(productos y clientes: usa el nombre tal como lo escribe el usuario)

Responde SOLO con un objeto JSON con estas claves:
{{
 "tipo": "consulta" | "ambigua" | "fuera_de_alcance" | "dimension_inexistente" | "operacion_no_autorizada" | "faltan_parametros",
 "operacion": "total" | "ranking" | "tendencia" | "comparacion_periodos" | "comparacion_miembros",
 "metrica": código | null,
 "dimension": código | null,
 "dimension_texto": texto de la dimensión pedida si NO existe en la lista | null,
 "periodo": {{"tipo": "todo|anio|semestre|trimestre|mes|rango|ultimos_meses|ytd", "anio": int|null, "numero": int|null,
             "desde": "AAAA-MM"|null, "hasta": "AAAA-MM"|null, "n": int|null}} | null,
 "periodo_comparacion": igual que periodo | null,
 "filtros": [{{"dimension": código, "valores": [..]}}],
 "orden": "asc" | "desc",
 "limite": int | null,
 "desglose": "mes" | null,
 "opciones": [..], "faltantes": [..], "motivo": "explicación breve", "supuestos": ["..."]
}}

Reglas:
1. Si el usuario pide borrar, modificar, insertar, crear, ver credenciales o ejecutar SQL: tipo="operacion_no_autorizada".
2. Si pide algo que no está en las métricas/dimensiones (inventario, empleados, clima, proveedores...): tipo="fuera_de_alcance".
3. Si pide agrupar por una dimensión que no existe (vendedor, método de pago, color...): tipo="dimension_inexistente" y dimension_texto.
4. Si no se puede saber el criterio ("¿cuál fue el mejor canal?"): tipo="ambigua", opciones={CRITERIOS_AMBIGUEDAD}.
5. Si pide comparar miembros sin decir cuáles ("compare dos canales") o "una categoría determinada" sin decir cuál: tipo="faltan_parametros".
6. Si no menciona periodo: "periodo": null (el sistema usará todo el rango y lo advertirá). No inventes periodos.
7. "¿Qué X tiene el mayor ...?" => operacion "ranking", limite 1. "las cinco ..." => limite 5. "menor/peor" => orden "asc".
8. "por mes", "mensual", "evolución" => dimension "mes", operacion "tendencia".
9. "redujo/creció/variación" de un grupo => operacion "comparacion_periodos" (si no hay periodos, déjalos null).
10. Comparar dos miembros (dos canales, dos categorías) => operacion "comparacion_miembros", dimension de esos miembros,
    filtro con ambos valores; si el periodo abarca varios meses usa desglose "mes".
"""


class InterpreteLLM(InterpreteBase):
    nombre = "llm"

    def __init__(self, modelo: str | None = None):
        if not CONFIG.llm_disponible:
            raise ErrorInterpretacion("No hay OPENROUTER_API_KEY configurada")
        from openai import OpenAI
        self._cliente = OpenAI(base_url=CONFIG.openrouter_base_url, api_key=CONFIG.openrouter_api_key,
                               timeout=CONFIG.llm_timeout, max_retries=1)
        self.modelo = modelo or CONFIG.openrouter_model
        self.ultima_respuesta_cruda = ""

    def _completar(self, mensajes: list[dict], json_mode: bool = True) -> str:
        kwargs = {"model": self.modelo, "messages": mensajes, "temperature": 0}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            r = self._cliente.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            if json_mode and "response_format" in str(e):
                kwargs.pop("response_format")
                r = self._cliente.chat.completions.create(**kwargs)
            else:
                raise ErrorInterpretacion(f"Fallo de OpenRouter: {e}") from e
        return r.choices[0].message.content or ""

    def interpretar(self, texto: str, meta, contexto: dict | None = None) -> dict:
        mensajes = [{"role": "system", "content": _prompt_sistema(meta)}]
        previa = (contexto or {}).get("ultima_intencion")
        if previa is not None:
            mensajes.append({"role": "system", "content": "Contexto de la pregunta anterior de la sesión (úsalo sólo "
                             f"si la nueva pregunta es de seguimiento, p. ej. '¿y en 2025?'): {json.dumps(intencion_a_datos(previa), ensure_ascii=False)}"})
        mensajes.append({"role": "user", "content": texto})
        crudo = self._completar(mensajes)
        self.ultima_respuesta_cruda = crudo
        m = re.search(r"\{.*\}", crudo, re.S)
        if not m:
            raise ErrorInterpretacion("El LLM no devolvió JSON")
        try:
            datos = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise ErrorInterpretacion(f"JSON inválido del LLM: {e}") from e
        if not isinstance(datos, dict) or "tipo" not in datos:
            raise ErrorInterpretacion("JSON del LLM sin la clave 'tipo'")
        return datos

    def redactar(self, pregunta: str, resumen: str, tabla_markdown: str) -> str:
        """Interpretación gerencial breve (2-3 oraciones). Se valida después con RV11."""
        mensajes = [
            {"role": "system", "content": "Eres analista de negocios. Escribe en español una interpretación gerencial "
             "BREVE (máximo 3 oraciones) del resultado. Usa EXCLUSIVAMENTE cifras que aparezcan en la tabla o el "
             "resumen; no inventes cifras, causas ni datos externos. Si sugieres una acción, que sea prudente. "
             "No uses viñetas ni encabezados."},
            {"role": "user", "content": f"Pregunta: {pregunta}\nResumen: {resumen}\nResultado:\n{tabla_markdown}"},
        ]
        return self._completar(mensajes, json_mode=False).strip()


class InterpreteHibrido(InterpreteBase):
    """Intenta con el LLM y, si falla, usa las reglas (degradación controlada)."""
    nombre = "hibrido"

    def __init__(self):
        self.reglas = InterpreteReglas()
        try:
            self.llm = InterpreteLLM()
        except ErrorInterpretacion:
            self.llm = None
        self.ultimo_origen = "reglas"
        self.ultimo_error = None

    def interpretar(self, texto: str, meta, contexto: dict | None = None) -> dict:
        if self.llm is not None:
            try:
                datos = self.llm.interpretar(texto, meta, contexto)
                self.ultimo_origen, self.ultimo_error = "llm", None
                return datos
            except ErrorInterpretacion as e:
                self.ultimo_error = str(e)
        self.ultimo_origen = "reglas"
        return self.reglas.interpretar(texto, meta, contexto)


def crear_interprete(modo: str | None = None) -> InterpreteBase:
    modo = (modo or CONFIG.modo_interprete).lower()
    if modo == "reglas":
        return InterpreteReglas()
    if modo == "llm":
        return InterpreteLLM()
    return InterpreteHibrido()
