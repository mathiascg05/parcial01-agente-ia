"""Pruebas unitarias (no requieren PostgreSQL salvo las marcadas como integración).   pytest -q"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente.bdoo.modelo import Analista, Gerente, Intencion, Pregunta, Sesion, Usuario  # noqa: E402
from agente.bdoo.reglas import ContextoValidacion, ReglaOperacionNoAutorizada, ReglaSQLSoloLectura  # noqa: E402
from agente.bdoo.tda import DocumentoIdentidad, ErrorTDA, Filtro, Periodo  # noqa: E402
from agente.bdoo.consultas import ConsultaRanking  # noqa: E402
from agente.datamart import MetadatosDataMart  # noqa: E402
from agente.interpretes.base import construir_intencion  # noqa: E402
from agente.interpretes.reglas_nl import InterpreteReglas  # noqa: E402

META = MetadatosDataMart(date(2025, 1, 1), date(2026, 9, 30), {
    "categoria": ["Alimentos", "Bebidas", "Hogar", "Jardinería", "Tecnología"],
    "canal": ["App móvil", "Delivery WhatsApp", "E-commerce web", "Mayorista B2B", "Tienda física"],
    "segmento": ["Corporativo", "Frecuente", "Minorista", "Premium"],
    "sucursal": ["Chacao", "La Candelaria"], "region": ["Capital", "Central"],
})


# ---------------------------------------------------------------------------------------- TDA
def test_documento_valida_formato():
    assert str(DocumentoIdentidad("v-12345678")) == "V-12345678"
    with pytest.raises(ErrorTDA):
        DocumentoIdentidad("12345678")


def test_periodo_invalido_y_ultimos_meses():
    with pytest.raises(ErrorTDA):
        Periodo(date(2026, 2, 1), date(2026, 1, 1))
    p = Periodo.ultimos_meses(3, date(2026, 9, 30))
    assert (p.desde, p.hasta) == (date(2026, 7, 1), date(2026, 9, 30))
    assert Periodo.del_trimestre(2026, 2).hasta == date(2026, 6, 30)


def test_filtro_rechaza_dimension_inexistente():
    with pytest.raises(ErrorTDA):
        Filtro("vendedor", ("Juan",))


# ---------------------------------------------------------------------------------------- objetos
def test_usuario_es_abstracto_y_polimorfico():
    with pytest.raises(TypeError):
        Usuario("x", "V-1234567")
    g, a = Gerente("G", "V-1234567"), Analista("A", "V-7654321")
    assert (g.nivel_detalle(), g.muestra_sql()) == ("ejecutivo", False)
    assert (a.nivel_detalle(), a.muestra_sql()) == ("tecnico", True)


def test_pregunta_maquina_de_estados():
    s = Sesion("S1", Gerente("G", "V-1234567"))
    p = s.nueva_pregunta("hola")
    assert isinstance(p, Pregunta) and p.estado == "RECIBIDA"
    with pytest.raises(ValueError):
        p.cambiar_estado("RESPONDIDA")      # no se puede responder sin interpretar
    p.asignar_intencion(Intencion("ambigua"))
    assert p.estado == "INTERPRETADA"


# ---------------------------------------------------------------------------------------- seguridad
@pytest.mark.parametrize("texto", ["Borra las ventas de enero", "DROP TABLE dm.fact_ventas", "actualiza el precio del café",
                                   "dame la contraseña de la base", "muéstrame oltp.cliente", "ventas'; delete from x; --"])
def test_rv01_bloquea_operaciones(texto):
    r = ReglaOperacionNoAutorizada().validar(ContextoValidacion(texto=texto))
    assert not r.aprobada


def test_rv01_permite_lectura():
    assert ReglaOperacionNoAutorizada().validar(ContextoValidacion(texto="¿Qué canal vende más?")).aprobada


@pytest.mark.parametrize("sql", ["DELETE FROM dm.fact_ventas", "SELECT * FROM oltp.cliente",
                                 "SELECT 1; DROP TABLE dm.dim_canal", "SELECT * FROM dm.fact_ventas -- x",
                                 "SELECT pg_sleep(10)", "WITH x AS (SELECT 1) SELECT * FROM control.etl_lote"])
def test_rv07_rechaza_sql_inseguro(sql):
    assert not ReglaSQLSoloLectura().validar(ContextoValidacion(texto="", sql=sql)).aprobada


def test_valores_de_filtro_van_como_parametros():
    """Un valor malicioso nunca se concatena en el SQL: viaja como parámetro."""
    i = construir_intencion({"tipo": "consulta", "operacion": "ranking", "metrica": "ingreso_neto", "dimension": "canal",
                             "filtros": [{"dimension": "categoria", "valores": ["x'); DROP TABLE dm.fact_ventas; --"]}]},
                            META, "test")
    sql, params = ConsultaRanking("CQ", "r", "", "", []).construir_sql(i)
    assert "DROP" not in sql and "x'); DROP TABLE dm.fact_ventas; --" in params["f0"]
    assert ReglaSQLSoloLectura().validar(ContextoValidacion(texto="", sql=sql)).aprobada


# ---------------------------------------------------------------------------------------- intérprete
@pytest.mark.parametrize("pregunta,esperado", [
    ("¿Cuál fue el ingreso neto por mes?", ("consulta", "tendencia", "ingreso_neto", "mes", None)),
    ("¿Cuáles son las cinco categorías con mayor margen bruto?", ("consulta", "ranking", "margen_bruto", "categoria", 5)),
    ("¿Qué sucursal presenta el ticket promedio más alto?", ("consulta", "ranking", "ticket_promedio", "sucursal", 1)),
    ("¿Qué segmento de clientes redujo más su volumen de compra?", ("consulta", "comparacion_periodos", "ingreso_neto", "segmento", None)),
    ("¿Qué canal concentra el mayor valor de ventas?", ("consulta", "ranking", "ingreso_neto", "canal", 1)),
    ("¿Cuál fue el mejor canal?", ("ambigua", None, None, "canal", None)),
    ("¿Cuál es el inventario por sucursal?", ("fuera_de_alcance", None, None, None, None)),
    ("ventas por vendedor", ("dimension_inexistente", None, "ingreso_neto", None, None)),
])
def test_interprete_reglas(pregunta, esperado):
    d = InterpreteReglas().interpretar(pregunta, META)
    obtenido = (d.get("tipo"), d.get("operacion"), d.get("metrica"), d.get("dimension"), d.get("limite"))
    assert obtenido == esperado


def test_intencion_sin_periodo_usa_rango_y_lo_marca():
    i = construir_intencion(InterpreteReglas().interpretar("ingreso neto por canal", META), META, "reglas")
    assert not i.periodo.explicito and i.periodo.hasta == date(2026, 9, 30)


def test_comparacion_de_dos_canales():
    d = InterpreteReglas().interpretar("Compare el margen de Tienda física y E-commerce web en los últimos tres meses", META)
    assert d["operacion"] == "comparacion_miembros" and d["dimension"] == "canal" and d["desglose"] == "mes"


# ---------------------------------------------------------------------------------------- regresiones
@pytest.mark.parametrize("texto", ["¿Qué productos debemos eliminar del catálogo por su bajo margen?",
                                   "¿Qué canal debería modificar su política de descuentos?", "Ventas de 2025; y de 2026"])
def test_rv01_permite_preguntas_de_negocio(texto):
    assert ReglaOperacionNoAutorizada().validar(ContextoValidacion(texto=texto)).aprobada


def test_margen_porcentual_y_anio_sin_de():
    d = InterpreteReglas().interpretar("Margen % por canal en el primer trimestre 2026", META)
    assert d["metrica"] == "margen_pct" and d["periodo"] == {"tipo": "trimestre", "numero": 1, "anio": 2026}


def test_numero_del_periodo_no_es_limite():
    d = InterpreteReglas().interpretar("¿Cuál es el ticket promedio por canal en los últimos tres meses?", META)
    assert d["limite"] is None and d["periodo"] == {"tipo": "ultimos_meses", "n": 3}


def test_anio_parcial_se_alinea():
    i = construir_intencion(InterpreteReglas().interpretar("crecimiento de ventas de 2026 respecto a 2025", META), META, "r")
    assert (i.periodo.hasta, i.periodo_comparacion.hasta) == (date(2026, 9, 30), date(2025, 9, 30))


# ---------------------------------------------------------------------------------------- anclaje del LLM
# Casos reales: salidas de gpt-4o-mini (OpenRouter, 29-10-2026) grabadas en docs/evidencias/llm_openrouter/.
from agente.interpretes.llm import anclar  # noqa: E402


def _anclar(texto, llm):
    return anclar(llm, InterpreteReglas().interpretar(texto, META), texto)


def test_anclaje_descarta_periodo_inventado():
    d, aj = _anclar("¿Cuál fue el ingreso neto por mes?", {"tipo": "consulta", "operacion": "tendencia",
                    "metrica": "ingreso_neto", "dimension": "mes", "periodo": {"tipo": "ultimos_meses", "n": 12}})
    assert d["periodo"] is None and aj


def test_anclaje_descarta_miembros_inventados():
    d, _ = _anclar("Compare el margen de dos canales durante los últimos tres meses disponibles.",
                   {"tipo": "consulta", "operacion": "comparacion_miembros", "metrica": "margen_bruto", "dimension": "canal",
                    "periodo": {"tipo": "ultimos_meses", "n": 3},
                    "filtros": [{"dimension": "canal", "valores": ["App móvil", "Delivery WhatsApp"]}]})
    assert d["tipo"] == "faltan_parametros"


def test_anclaje_normaliza_esquema_y_toma_dimension_literal():
    d, _ = _anclar("¿Qué categoría tiene el menor margen porcentual?",
                   {"tipo": "ranking", "operacion": "ranking", "metrica": "margen_pct", "orden": "asc"})
    assert (d["tipo"], d["operacion"], d["dimension"]) == ("consulta", "ranking", "categoria")


def test_anclaje_reubica_valor_en_su_dimension():
    d, _ = _anclar("¿Qué tanto descuento dimos en E-commerce web durante 2026?",
                   {"tipo": "consulta", "operacion": "total", "metrica": "descuento_pct", "periodo": {"tipo": "anio", "anio": 2026},
                    "filtros": [{"dimension": "tipo_canal", "valores": ["E-commerce web"]}]})
    assert d["filtros"] == [{"dimension": "canal", "valores": ["E-commerce web"]}]


def test_anclaje_respeta_al_llm_cuando_las_reglas_no_entienden():
    texto = "¿Cómo le fue a Tecnología en julio de 2026 comparado con julio de 2025?"
    llm = {"tipo": "consulta", "operacion": "comparacion_periodos", "metrica": "ingreso_neto",
           "periodo": {"tipo": "mes", "anio": 2026, "numero": 7}, "periodo_comparacion": {"tipo": "mes", "anio": 2025, "numero": 7},
           "filtros": [{"dimension": "categoria", "valores": ["Tecnología"]}]}
    d, _ = _anclar(texto, llm)
    assert d["periodo"] == llm["periodo"] and d["metrica"] == "ingreso_neto"


def test_total_con_dimension_es_ranking():
    i = construir_intencion({"tipo": "consulta", "operacion": "total", "metrica": "ingreso_neto", "dimension": "canal"}, META, "x")
    assert i.operacion == "ranking"
