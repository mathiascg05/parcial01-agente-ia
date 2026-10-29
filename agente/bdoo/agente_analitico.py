"""
AgenteAnalitico: objeto persistente que COORDINA interpretación, consulta, validación y respuesta.

Flujo (sección 2.1 del enunciado):
 1. Recepción de la pregunta (Pregunta en la Sesion)               -> RV01 sobre el texto
 2. Identificación de intención, métrica, dimensión, periodo, filtros (intérprete LLM/reglas)
                                                                    -> RV02..RV06 sobre la intención
 3. Selección de consulta parametrizada del catálogo (aplica_a polimórfico) -> RV07 sobre el SQL
 4. Ejecución sobre el Data Mart (rol de solo lectura)
 5. Validación del resultado y manejo de errores                   -> RV08..RV10
 6. Respuesta gerencial con datos, contexto y fuente (+ RV11 si hay narrativa del LLM)
 7. Registro de la interacción en los objetos persistentes (se confirma con la transacción ZODB)

Los servicios técnicos (conexión al Data Mart, intérprete, LLM) NO se persisten: se inyectan en cada
llamada (ServiciosAgente). En la BDOO sólo queda el estado y la trazabilidad.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from persistent.list import PersistentList
from persistent.mapping import PersistentMapping

from agente.bdoo.modelo import FuenteDato, Intencion, ObjetoAgente, RespuestaAgente, _ref
from agente.bdoo.reglas import ContextoValidacion
from agente.catalogo import DIMENSIONES, METRICAS, describir_capacidades
from agente.interpretes.base import ErrorInterpretacion, construir_intencion
from agente.redactor import resumen_y_interpretacion, tabla_markdown


@dataclass
class ServiciosAgente:
    datamart: object
    interprete: object
    narrador_llm: object = None     # InterpreteLLM con método redactar(), opcional


class AgenteAnalitico(ObjetoAgente):
    def __init__(self, nombre: str, catalogo: list, reglas: list, fuentes: dict, version: str = "1.0"):
        super().__init__()
        self._nombre = nombre
        self._version = version
        self._catalogo = PersistentList(catalogo)
        self._reglas = PersistentList(reglas)
        self._fuentes = PersistentMapping(fuentes)        # tabla -> FuenteDato (objetos compartidos)
        self._estadisticas = PersistentMapping()

    nombre = property(lambda s: s._nombre)
    version = property(lambda s: s._version)
    catalogo = property(lambda s: list(s._catalogo))
    reglas = property(lambda s: list(s._reglas))
    fuentes = property(lambda s: dict(s._fuentes))
    estadisticas = property(lambda s: dict(s._estadisticas))

    def consulta(self, codigo: str):
        return next((c for c in self._catalogo if c.codigo == codigo), None)

    def regla(self, codigo: str):
        return next((r for r in self._reglas if r.codigo == codigo), None)

    # ------------------------------------------------------------------------------------------
    def _validar(self, momento: str, ctx: ContextoValidacion, respuesta_validaciones: list):
        """Recorre la cadena de reglas del momento. Devuelve la primera falla bloqueante (o None)."""
        bloqueo = None
        for regla in self._reglas:
            if regla.momento != momento:
                continue
            res = regla.aplicar(ctx)
            if res is None:
                continue
            respuesta_validaciones.append(res)
            if not res.aprobada and res.severidad == "bloqueante" and bloqueo is None:
                bloqueo = res
                break
        return bloqueo

    def _seleccionar_consulta(self, intencion: Intencion):
        for consulta in self._catalogo:            # selección polimórfica
            if consulta.aplica_a(intencion):
                return consulta
        return None

    def _contar(self, clave: str) -> None:
        self._estadisticas[clave] = self._estadisticas.get(clave, 0) + 1

    # ------------------------------------------------------------------------------------------
    def responder(self, sesion, texto: str, servicios: ServiciosAgente):
        meta = servicios.datamart.metadatos()
        pregunta = sesion.nueva_pregunta(texto)
        validaciones: list = []
        ctx = ContextoValidacion(texto=texto, metadatos=meta)

        def cerrar(respuesta: RespuestaAgente, intencion: Intencion | None = None):
            for v in validaciones:
                respuesta.registrar_validacion(v)
                if not v.aprobada and v.severidad == "advertencia":
                    respuesta.agregar_advertencia(v.mensaje)
            if intencion is not None and pregunta.intencion is None:
                pregunta.asignar_intencion(intencion)
            pregunta.asignar_respuesta(respuesta)
            self._contar(respuesta.tipo)
            return pregunta

        # 1) Texto: operación no autorizada
        bloqueo = self._validar("texto", ctx, validaciones)
        if bloqueo:
            intencion = Intencion("operacion_no_autorizada", motivo=bloqueo.mensaje, origen="regla RV01")
            return cerrar(RespuestaAgente("RECHAZO", bloqueo.mensaje), intencion)

        # 2) Interpretación
        try:
            datos = servicios.interprete.interpretar(texto, meta, sesion.contexto())
            origen = getattr(servicios.interprete, "ultimo_origen", None) or servicios.interprete.nombre
            intencion = construir_intencion(datos, meta, origen)
        except ErrorInterpretacion as e:
            intencion = Intencion("ambigua", motivo=f"No se pudo interpretar la pregunta ({e}).", origen="error")
        pregunta.asignar_intencion(intencion, seguimiento=bool(any("seguimiento" in s for s in intencion.supuestos)))
        ctx.intencion = intencion

        if intencion.tipo == "operacion_no_autorizada":
            msg = intencion.motivo or "Operación no autorizada: el agente sólo consulta datos (lectura)."
            return cerrar(RespuestaAgente("RECHAZO", f"Operación no autorizada. {msg}"))

        bloqueo = self._validar("intencion", ctx, validaciones)
        if bloqueo:
            if bloqueo.regla == "RV02":
                r = RespuestaAgente("RECHAZO", f"{bloqueo.mensaje} No tengo datos para responder eso y no voy a "
                                               f"inventarlo. {describir_capacidades()}")
            elif bloqueo.regla == "RV03":
                dims = ", ".join(d.nombre.lower() for d in DIMENSIONES.values())
                r = RespuestaAgente("RECHAZO", f"{bloqueo.mensaje} Las dimensiones disponibles son: {dims}.")
            elif bloqueo.regla == "RV05":
                r = RespuestaAgente("ACLARACION", bloqueo.mensaje)
            else:  # RV04 ambigüedad / parámetros faltantes
                r = RespuestaAgente("ACLARACION", f"{bloqueo.mensaje} ¿Con qué criterio desea evaluarlo?"
                                    if intencion.tipo == "ambigua" else bloqueo.mensaje)
                r.definir_opciones(list(intencion.opciones))
            for s in intencion.supuestos:
                r.agregar_advertencia(s)
            return cerrar(r)

        # 3) Selección y construcción de la consulta
        consulta = self._seleccionar_consulta(intencion)
        if consulta is None:
            return cerrar(RespuestaAgente("ERROR", "No existe una consulta del catálogo para esta intención."))
        sql, params = consulta.construir_sql(intencion)
        ctx.sql, ctx.parametros = sql, params
        bloqueo = self._validar("sql", ctx, validaciones)
        if bloqueo:
            return cerrar(RespuestaAgente("RECHAZO", f"Consulta bloqueada por seguridad: {bloqueo.mensaje}"))

        # 4) Ejecución
        resultado = consulta.ejecutar(servicios.datamart, intencion, sql, params)
        ctx.resultado = resultado

        # Total de control independiente para métricas aditivas agrupadas sin límite
        m = METRICAS[intencion.metrica]
        if (m.aditividad == "aditiva" and intencion.dimension and not intencion.limite
                and consulta.operacion in ("ranking", "tendencia") and not resultado.tiene_error()):
            p_ctrl: dict = {}
            sql_ctrl = (f"SELECT {m.expresion} AS total\n{consulta._from(consulta._aliases(intencion))}\n"
                        f"{consulta._where(intencion, p_ctrl)}")
            try:
                _, filas, _ = servicios.datamart.ejecutar(sql_ctrl, p_ctrl)
                ctx.control_total = filas[0][0] if filas and filas[0][0] is not None else None
            except Exception:  # noqa: BLE001
                ctx.control_total = None

        # 5) Validación del resultado
        bloqueo = self._validar("resultado", ctx, validaciones)
        if bloqueo:
            if resultado.tiene_error():
                r = RespuestaAgente("ERROR", f"No fue posible ejecutar la consulta: {resultado.error}")
            else:
                r = RespuestaAgente("SIN_DATOS", f"No hay registros en el Data Mart para {m.nombre.lower()}"
                                    + (f" con {'; '.join(f.describir() for f in intencion.filtros)}" if intencion.filtros else "")
                                    + f" en {intencion.periodo}"
                                    + (f" vs {intencion.periodo_comparacion}" if intencion.periodo_comparacion else "")
                                    + ". El resultado está vacío: no se reporta como cero porque no hubo ventas "
                                      "registradas que lo respalden.")
            self._documentar(r, intencion, consulta, sql, params, resultado)
            return cerrar(r)

        # 6) Respuesta gerencial
        resumen, interp = resumen_y_interpretacion(intencion, resultado)
        r = RespuestaAgente("RESPUESTA", resumen)
        for aviso in self._avisos_incompletos(intencion, resultado):
            r.agregar_advertencia(aviso)
        r.asignar_interpretacion(interp, "plantilla")
        self._documentar(r, intencion, consulta, sql, params, resultado)
        if servicios.narrador_llm is not None:
            try:
                texto_llm = servicios.narrador_llm.redactar(texto, resumen, tabla_markdown(resultado, intencion.metrica))
                ctx.narrativa = texto_llm
                fallo = self._validar("narrativa", ctx, validaciones)
                ultima = validaciones[-1] if validaciones and validaciones[-1].regla == "RV11" else None
                if fallo is None and ultima is not None and ultima.aprobada:
                    r.asignar_interpretacion(texto_llm, "llm")
            except Exception as e:  # noqa: BLE001
                r.agregar_advertencia(f"No se pudo generar la narrativa con el LLM ({type(e).__name__}); "
                                      f"se usó la plantilla.")
        sesion.recordar(intencion)
        return cerrar(r)

    @staticmethod
    def _avisos_incompletos(intencion, resultado) -> list[str]:
        """Miembros pedidos sin registros y comparaciones con un lado vacío: se informan, nunca se asumen cero."""
        avisos = []
        filas = resultado.como_dicts()
        if intencion.operacion == "comparacion_miembros" and intencion.dimension:
            filtro = intencion.filtro_de(intencion.dimension)
            presentes = {str(f.get(intencion.dimension)) for f in filas}
            for v in (filtro.valores if filtro else ()):
                if v not in presentes:
                    avisos.append(f"{v} no registra ventas en {intencion.periodo}: no aparece en la comparación "
                                  f"(sin datos; no se reporta como cero).")
        if intencion.operacion == "comparacion_periodos":
            clave = intencion.dimension or "total"
            sin_base = [str(f.get(clave)) for f in filas if f.get("valor_base") is None]
            sin_act = [str(f.get(clave)) for f in filas if f.get("valor_actual") is None]
            if sin_base:
                avisos.append(f"Sin registros en {intencion.periodo_comparacion} para: {', '.join(sin_base)}. Su variación "
                              f"no se calcula (no se asume cero).")
            if sin_act:
                avisos.append(f"Sin registros en {intencion.periodo} para: {', '.join(sin_act)}. Su variación no se calcula.")
        return avisos

    def _documentar(self, r: RespuestaAgente, intencion, consulta, sql, params, resultado):
        m = METRICAS[intencion.metrica]
        r.documentar_metrica(m.nombre, m.regla)
        dim = DIMENSIONES[intencion.dimension].nombre if intencion.dimension else ""
        if intencion.desglose:
            dim += f" (desglose por {DIMENSIONES[intencion.desglose].nombre.lower()})"
        per = str(intencion.periodo) + (f" vs {intencion.periodo_comparacion}" if intencion.periodo_comparacion else "")
        r.documentar_contexto(per, "; ".join(f.describir() for f in intencion.filtros), dim)
        r.documentar_consulta(f"{consulta.codigo} v{consulta.version} ({consulta.nombre})", sql, params)
        r.asignar_resultado(resultado)
        for tabla in sorted(set(re.findall(r"\bdm\.\w+", sql))):
            fuente = self._fuentes.get(tabla)
            if isinstance(fuente, FuenteDato):
                r.agregar_fuente(fuente)
        for s in intencion.supuestos:
            r.agregar_advertencia(s)

    def describir(self) -> str:
        return f"{self._nombre} v{self._version} ({len(self._catalogo)} consultas, {len(self._reglas)} reglas)"

    def a_dict(self) -> dict:
        return {**super().a_dict(), "nombre": self._nombre, "version": self._version,
                "catalogo": [f"{c.codigo} ({c.clase}) ido={c.ido}" for c in self._catalogo],
                "reglas": [f"{r.codigo} ({r.clase}) ido={r.ido}" for r in self._reglas],
                "fuentes_ido": {k: _ref(v) for k, v in self._fuentes.items()},
                "estadisticas": dict(self._estadisticas)}
