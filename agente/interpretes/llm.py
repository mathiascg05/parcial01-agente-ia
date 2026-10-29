"""
Intérprete con LLM vía OpenRouter (API compatible con OpenAI).

El LLM SÓLO traduce la pregunta a un JSON con códigos del catálogo. No ve la base de datos, no
escribe SQL y su salida es tratada como dato no confiable: se valida con construir_intencion() y con
las reglas RV02–RV06. Si la llamada falla o el JSON es inválido, el intérprete híbrido usa las reglas.

Además, el intérprete híbrido ANCLA la salida del LLM a la lectura literal de la pregunta (anclar()): la
validación con respuestas reales de gpt-4o-mini mostró periodos y miembros inventados y confusiones de
esquema; el LLM sólo aporta lo que no contradiga lo escrito por el usuario. Ver docs/evidencias/validacion_llm.md.
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
    filtro con ambos valores; desglose "mes" sólo si el periodo es "últimos N meses", un trimestre, un semestre o un
    rango, o si el usuario pide la evolución mensual (para un año completo, sin desglose).
11. "ventas", "vendimos", "valor de ventas", "lidera las ventas", "crecimiento de ventas" => metrica "ingreso_neto"
    (usa monto_bruto o unidades SÓLO si el usuario dice "bruto" o "unidades").
12. NUNCA pongas en "filtros" un valor que el usuario no escribió. "dos canales" sin nombrarlos => "faltan_parametros".
13. Si la pregunta no contiene ninguna expresión de tiempo, "periodo" DEBE ser null (también con "por mes").
14. "último semestre" / "último trimestre" sin año => periodo {{"tipo": "ultimos_meses", "n": 6}} / {{"tipo": "ultimos_meses", "n": 3}}.
15. Un año o periodo sin datos (p. ej. 2024) NO es fuera_de_alcance: devuelve la consulta con ese periodo (el sistema avisa).
16. Una dimensión que no existe (vendedor, método de pago) es "dimension_inexistente", no "fuera_de_alcance".
17. "redujo", "cayó", "disminuyó", "menor", "peor", "más bajo" => orden "asc".
18. "cada canal", "por región" => operacion "ranking"; "tendencia" sólo con dimensiones de tiempo (mes, trimestre...).
19. "una categoría y periodo determinados" sin decir cuáles => "faltan_parametros" con faltantes (no "ambigua").
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
    """LLM + anclaje literal; si el LLM falla o no hay API key, usa las reglas (degradación controlada)."""
    nombre = "hibrido"

    def __init__(self):
        self.reglas = InterpreteReglas()
        try:
            self.llm = InterpreteLLM()
        except ErrorInterpretacion:
            self.llm = None
        self.ultimo_origen = "reglas"
        self.ultimo_error = None
        self.ultimos_ajustes: list[str] = []

    def interpretar(self, texto: str, meta, contexto: dict | None = None) -> dict:
        self.ultimos_ajustes = []
        literal = self.reglas.interpretar(texto, meta, contexto)
        if self.llm is not None:
            # El LLM aporta comprensión semántica; la lectura literal (reglas) sirve de ancla para los hechos
            # escritos en la pregunta. Ver anclar() y docs/evidencias/validacion_llm.md.
            try:
                datos = self.llm.interpretar(texto, meta, contexto)
                self.ultimo_origen, self.ultimo_error = "llm", None
                datos, self.ultimos_ajustes = anclar(datos, literal, texto, contexto)
                if self.ultimos_ajustes:
                    self.ultimo_origen = "llm+anclaje"
                return datos
            except ErrorInterpretacion as e:
                self.ultimo_error = str(e)
        self.ultimo_origen = "reglas"
        return literal


# ---------------------------------------------------------------------------------------------
# Anclaje (grounding) de la salida del LLM
# ---------------------------------------------------------------------------------------------
# La validación con un LLM real (gpt-4o-mini vía OpenRouter, 29-10-2026) mostró que el modelo, aun con
# instrucciones explícitas, a veces inventa periodos ("últimos 12 meses" en "ingreso neto por mes"),
# inventa miembros ("compare dos canales" -> App móvil y Delivery WhatsApp) o interpreta "ventas" como
# venta bruta o unidades. Por eso el LLM aporta la comprensión semántica (operación, métrica, dimensión),
# pero los HECHOS LITERALES de la pregunta (fechas, valores de filtro, sentido del orden) se contrastan
# con el extractor determinista: todo lo que el LLM proponga y no esté anclado en el texto (o en el
# contexto de la sesión) se descarta, y cada ajuste queda registrado como supuesto visible.
_TIPOS = {"consulta", "ambigua", "fuera_de_alcance", "dimension_inexistente", "operacion_no_autorizada",
          "faltan_parametros"}
_OPERACIONES = {"total", "ranking", "tendencia", "comparacion_periodos", "comparacion_miembros"}


def _norm(x) -> str:
    from agente.datamart import normalizar
    return normalizar(x)


def _anclado(valor, texto_n: str, literales: set[str]) -> bool:
    v = _norm(valor)
    return bool(v) and (v in texto_n or v in literales)


def anclar(llm: dict, literal: dict, texto: str, contexto: dict | None = None) -> tuple[dict, list[str]]:
    """Contrasta la interpretación del LLM con la extracción literal por reglas. Devuelve (datos, ajustes)."""
    datos = dict(llm)
    ajustes: list[str] = []
    texto_n = _norm(texto)

    # 0. Esquema: el modelo a veces pone la operación en "tipo" ("ranking", "comparacion_miembros").
    if datos.get("tipo") not in _TIPOS and (datos.get("operacion") in _OPERACIONES or datos.get("tipo") in _OPERACIONES):
        datos["operacion"] = datos.get("operacion") if datos.get("operacion") in _OPERACIONES else datos["tipo"]
        datos["tipo"] = "consulta"
    t_lit, t_llm = literal.get("tipo"), datos.get("tipo")

    # 1. Tipo: cuando la lectura literal es más específica que el LLM, prevalece. (El texto ya pasó RV01,
    #    así que un "operacion_no_autorizada" del LLM sobre una dimensión o tema detectado literalmente es
    #    un falso positivo; sobre una consulta normal se respeta, por prudencia.)
    reconocida = t_lit == "consulta" and literal.get("metrica") and (
        literal.get("dimension") or literal.get("periodo") or literal.get("filtros"))
    if t_llm == "fuera_de_alcance" and (t_lit == "dimension_inexistente" or reconocida):
        ajustes.append(f"El LLM marcó la pregunta como fuera de alcance, pero nombra elementos del catálogo; "
                       f"se usó la lectura literal ({t_lit}).")
        return _con_supuestos(literal, ajustes), ajustes
    if t_llm == "operacion_no_autorizada" and t_lit in ("dimension_inexistente", "fuera_de_alcance"):
        ajustes.append(f"El LLM la marcó como operación no autorizada; la lectura literal es {t_lit}.")
        return _con_supuestos(literal, ajustes), ajustes
    if t_llm == "ambigua" and t_lit == "faltan_parametros":
        ajustes.append("El LLM la marcó como ambigua; se pidió el parámetro faltante concreto.")
        return _con_supuestos(literal, ajustes), ajustes
    if t_llm == "ambigua" and t_lit == "consulta" and literal.get("metrica"):
        ajustes.append(f"El LLM pidió el criterio, pero la pregunta lo nombra ({literal['metrica']}); se usó la lectura literal.")
        return _con_supuestos(literal, ajustes), ajustes
    if t_llm == t_lit and t_llm in ("faltan_parametros", "ambigua"):
        # Misma conclusión: se usan las opciones deterministas del catálogo (el LLM no siempre las lista).
        return literal, ajustes
    if t_llm != "consulta":
        return datos, ajustes

    # 2. Filtros: sólo valores escritos por el usuario (o heredados del contexto / detectados por reglas).
    literales = {_norm(v) for f in literal.get("filtros") or [] for v in f.get("valores") or []}
    previa = (contexto or {}).get("ultima_intencion")
    if previa is not None:
        literales |= {_norm(v) for f in intencion_a_datos(previa).get("filtros") or [] for v in f.get("valores") or []}
    dim_literal = {_norm(v): f["dimension"] for f in literal.get("filtros") or [] for v in f.get("valores") or []}
    nuevos = []
    for f in _reubicar(datos.get("filtros") or [], dim_literal, ajustes):
        buenos = [v for v in f.get("valores") or [] if _anclado(v, texto_n, literales)]
        malos = [v for v in f.get("valores") or [] if v not in buenos]
        if malos:
            ajustes.append(f"Se descartaron valores de filtro no mencionados en la pregunta: {', '.join(map(str, malos))}.")
        if buenos:
            nuevos.append({**f, "valores": buenos})
    nuevos = _fusionar(nuevos)
    dims_llm = {f["dimension"] for f in nuevos}
    for f in literal.get("filtros") or []:
        if f.get("dimension") not in dims_llm:
            nuevos.append(f)
            ajustes.append(f"Se agregó el filtro escrito en la pregunta: {f['dimension']} = {', '.join(map(str, f['valores']))}.")
    datos["filtros"] = nuevos
    if datos.get("operacion") == "comparacion_miembros":
        n = sum(len(f["valores"]) for f in nuevos if f["dimension"] == datos.get("dimension"))
        if n < 2:
            if t_lit == "consulta" and literal.get("operacion") == "comparacion_miembros":
                ajustes.append("Los miembros a comparar se tomaron literalmente de la pregunta.")
                return _con_supuestos(literal, ajustes), ajustes
            ajustes.append("Faltan los miembros a comparar (el LLM los había supuesto).")
            if t_lit == "faltan_parametros":
                return _con_supuestos(literal, ajustes), ajustes
            return _con_supuestos({"tipo": "faltan_parametros", "metrica": datos.get("metrica"),
                                   "dimension": datos.get("dimension"), "faltantes": [datos.get("dimension")]},
                                  ajustes), ajustes

    # Lo que sigue usa la lectura literal como referencia sólo si las reglas entendieron la pregunta completa;
    # si no (p. ej. la marcaron ambigua), la interpretación del LLM se respeta y sólo se completan omisiones.
    confiable = t_lit == "consulta"

    # 3. Periodos: el extractor de fechas es determinista y está probado; prevalece si hay discrepancia.
    for clave in ("periodo", "periodo_comparacion") if confiable else ():
        p_llm, p_lit = datos.get(clave), literal.get(clave)
        if p_llm and p_llm.get("tipo") == "todo":
            p_llm = None
        if p_lit:
            if _resumen_periodo(p_llm) != _resumen_periodo(p_lit):
                if p_llm:
                    ajustes.append(f"Periodo ajustado a lo escrito en la pregunta ({clave}).")
                datos[clave] = p_lit
        elif p_llm and previa is None:
            ajustes.append("Se descartó un periodo que la pregunta no menciona (el LLM lo había supuesto).")
            datos[clave] = None

    # 4a. Métrica omitida por el LLM pero reconocible en el texto.
    if not datos.get("metrica") and literal.get("metrica"):
        datos["metrica"] = literal["metrica"]
        ajustes.append(f"Se tomó la métrica escrita en la pregunta ({literal['metrica']}).")

    # 4b. Glosario de negocio: "ventas" = ingreso neto, salvo que se pida bruto o unidades.
    if (datos.get("metrica") in ("monto_bruto", "unidades") and literal.get("metrica") == "ingreso_neto"
            and re.search(r"\bvent|\bvend|volumen de compra", texto_n) and not re.search(r"brut|unidad", texto_n)):
        ajustes.append(f"'Ventas' / 'volumen de compra' se midió como ingreso neto (glosario del Data Mart), "
                       f"no como {datos['metrica']}.")
        datos["metrica"] = "ingreso_neto"

    # 5. Sentido del orden explícito en el texto (redujo, menor, peor...).
    if confiable and literal.get("orden") == "asc" and datos.get("orden") != "asc":
        ajustes.append("Orden ascendente (la pregunta pide el menor / la mayor reducción).")
        datos["orden"] = "asc"

    # 5b. Variación entre periodos: "redujo", "creció", "vs" son marcas literales de comparación temporal.
    if confiable and literal.get("operacion") == "comparacion_periodos" and datos.get("operacion") in ("ranking", "total"):
        datos["operacion"] = "comparacion_periodos"
        ajustes.append("La pregunta pide una variación entre periodos (redujo / creció / vs).")

    if confiable and literal.get("operacion") == "tendencia" and datos.get("operacion") == "total":
        datos["operacion"], datos["dimension"] = "tendencia", literal.get("dimension")
        ajustes.append(f"La pregunta pide la serie temporal ('por {literal.get('dimension')}').")

    # 5c. Desglose temporal de una comparación entre miembros: regla de presentación determinista.
    if datos.get("operacion") == "comparacion_miembros" and literal.get("operacion") == "comparacion_miembros":
        datos["desglose"] = literal.get("desglose")

    # 6. Dimensión omitida por el LLM pero escrita en la pregunta ("¿qué estado...?").
    if (confiable and not datos.get("dimension") and literal.get("dimension") and datos.get("operacion") == "total"
            and literal.get("operacion") in ("ranking", "tendencia")):
        datos["operacion"], datos["limite"] = literal["operacion"], literal.get("limite")
    if not datos.get("dimension") and literal.get("dimension") and datos.get("operacion") != "total":
        datos["dimension"] = literal["dimension"]
        if datos.get("operacion") == "ranking" and literal.get("operacion") == "comparacion_periodos":
            datos["operacion"] = "comparacion_periodos"
        ajustes.append(f"Se tomó la dimensión escrita en la pregunta ({literal['dimension']}).")

    # 6b. Límite explícito ("el día con más", "top 3") que el LLM no trasladó.
    if not datos.get("limite") and literal.get("limite") and datos.get("dimension") == literal.get("dimension"):
        datos["limite"] = literal["limite"]

    # 7. "Tendencia" sólo tiene sentido sobre el tiempo.
    if datos.get("operacion") == "tendencia" and datos.get("dimension") not in ("mes", "trimestre", "semestre", "anio", None):
        datos["operacion"] = "ranking"
    elif datos.get("operacion") == "tendencia" and not datos.get("dimension") and literal.get("operacion"):
        datos["operacion"] = literal["operacion"]
        datos["dimension"] = literal.get("dimension")
    if datos.get("operacion") == "ranking" and not datos.get("dimension"):
        datos["operacion"] = literal.get("operacion") or "total"
        datos["dimension"] = literal.get("dimension")
    return _con_supuestos(datos, ajustes), ajustes


def _reubicar(filtros: list[dict], dim_literal: dict[str, str], ajustes: list[str]) -> list[dict]:
    """Si el LLM puso un valor en la dimensión equivocada ('Premium' como tipo de cliente) y la lectura
    literal lo encontró en el catálogo de otra dimensión (segmento), se mueve a esa dimensión."""
    salida = []
    for f in filtros:
        if not isinstance(f, dict):
            continue
        valores = f.get("valores") or []
        for v in valores if isinstance(valores, list) else [valores]:
            dim = dim_literal.get(_norm(v), f.get("dimension"))
            if not dim:
                continue
            if dim != f.get("dimension"):
                ajustes.append(f"'{v}' es un valor de {dim}, no de {f.get('dimension')}.")
            salida.append({"dimension": dim, "valores": [v]})
    return salida


def _fusionar(filtros: list[dict]) -> list[dict]:
    por_dim: dict[str, list] = {}
    for f in filtros:
        por_dim.setdefault(f["dimension"], [])
        por_dim[f["dimension"]] += [v for v in f["valores"] if v not in por_dim[f["dimension"]]]
    return [{"dimension": d, "valores": v} for d, v in por_dim.items()]


def _resumen_periodo(p: dict | None):
    if not p:
        return None
    return tuple((k, p.get(k)) for k in ("tipo", "anio", "numero", "desde", "hasta", "n") if p.get(k) is not None)


def _con_supuestos(datos: dict, ajustes: list[str]) -> dict:
    d = dict(datos)
    if ajustes:
        d["supuestos"] = list(d.get("supuestos") or []) + [f"Anclaje: {a}" for a in ajustes]
    return d


def crear_interprete(modo: str | None = None) -> InterpreteBase:
    modo = (modo or CONFIG.modo_interprete).lower()
    if modo == "reglas":
        return InterpreteReglas()
    if modo == "llm":
        return InterpreteLLM()
    return InterpreteHibrido()
