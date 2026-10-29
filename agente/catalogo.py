"""
Capa semántica del agente: LISTAS BLANCAS de métricas, dimensiones, tablas y joins permitidos.

Ningún identificador SQL (tabla, columna, expresión) proviene del texto del usuario ni del LLM:
el intérprete sólo puede devolver CÓDIGOS de este catálogo, y el constructor de consultas traduce
esos códigos a SQL. Los valores (fechas, categorías, canales...) viajan siempre como parámetros.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------
# Tablas autorizadas (todas en el esquema dm). Cualquier otra referencia es rechazada (RV07).
# ---------------------------------------------------------------------------------------------
TABLAS_AUTORIZADAS = {
    "dm.fact_ventas": "v",
    "dm.dim_fecha": "f",
    "dm.dim_producto": "p",
    "dm.dim_cliente": "c",
    "dm.dim_sucursal": "s",
    "dm.dim_canal": "n",
}

JOINS = {
    "f": "JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk",
    "p": "JOIN dm.dim_producto p ON p.producto_sk = v.producto_sk",
    "c": "JOIN dm.dim_cliente c ON c.cliente_sk = v.cliente_sk",
    "s": "JOIN dm.dim_sucursal s ON s.sucursal_sk = v.sucursal_sk",
    "n": "JOIN dm.dim_canal n ON n.canal_sk = v.canal_sk",
}

TABLA_POR_ALIAS = {alias: tabla for tabla, alias in TABLAS_AUTORIZADAS.items()}


@dataclass(frozen=True)
class Metrica:
    codigo: str
    nombre: str
    expresion: str             # expresión SQL agregada (lista blanca)
    aditividad: str            # aditiva | semiaditiva | no aditiva
    formato: str               # usd | entero | pct
    regla: str                 # regla de cálculo documentada
    campos: tuple              # campos del hecho utilizados
    intencion: str             # intención analítica por defecto
    alias_requeridos: tuple = ()
    orden_natural: str = "desc"  # qué significa "mejor" para esta métrica


METRICAS: dict[str, Metrica] = {m.codigo: m for m in [
    Metrica("ingreso_neto", "Ingreso neto", "SUM(v.ingreso_neto)", "aditiva", "usd",
            "SUM(cantidad × precio_unitario − descuento), sin impuestos, sólo tickets completados",
            ("ingreso_neto",), "analizar_ventas"),
    Metrica("monto_bruto", "Venta bruta", "SUM(v.monto_bruto)", "aditiva", "usd",
            "SUM(cantidad × precio_unitario), antes de descuentos", ("monto_bruto",), "analizar_ventas"),
    Metrica("descuento", "Descuento otorgado", "SUM(v.descuento)", "aditiva", "usd",
            "SUM(descuento de cada línea)", ("descuento",), "analizar_ventas", (), "asc"),
    Metrica("descuento_pct", "Porcentaje de descuento",
            "ROUND(SUM(v.descuento) / NULLIF(SUM(v.monto_bruto), 0) * 100, 2)", "no aditiva", "pct",
            "SUM(descuento) / SUM(monto_bruto) × 100 (se recalcula, nunca se promedia)",
            ("descuento", "monto_bruto"), "analizar_rentabilidad", (), "asc"),
    Metrica("costo", "Costo de ventas", "SUM(v.costo_total)", "aditiva", "usd",
            "SUM(cantidad × costo_unitario)", ("costo_total",), "analizar_rentabilidad", (), "asc"),
    Metrica("margen_bruto", "Margen bruto", "SUM(v.margen_bruto)", "aditiva", "usd",
            "SUM(ingreso_neto − costo_total)", ("margen_bruto",), "analizar_rentabilidad"),
    Metrica("margen_pct", "Margen bruto %",
            "ROUND(SUM(v.margen_bruto) / NULLIF(SUM(v.ingreso_neto), 0) * 100, 2)", "no aditiva", "pct",
            "SUM(margen_bruto) / SUM(ingreso_neto) × 100 (se recalcula, nunca se promedia)",
            ("margen_bruto", "ingreso_neto"), "analizar_rentabilidad"),
    Metrica("ticket_promedio", "Ticket promedio",
            "ROUND(SUM(v.ingreso_neto) / NULLIF(COUNT(DISTINCT v.numero_ticket), 0), 2)", "no aditiva", "usd",
            "SUM(ingreso_neto) / COUNT(DISTINCT numero_ticket)", ("ingreso_neto", "numero_ticket"),
            "analizar_ventas"),
    Metrica("unidades", "Unidades vendidas", "SUM(v.cantidad)", "aditiva", "entero",
            "SUM(cantidad)", ("cantidad",), "analizar_ventas"),
    Metrica("transacciones", "Número de transacciones (tickets)", "COUNT(DISTINCT v.numero_ticket)",
            "no aditiva", "entero", "COUNT(DISTINCT numero_ticket) — no se suman entre grupos (un ticket "
            "puede tener varias categorías)", ("numero_ticket",), "analizar_ventas"),
    Metrica("clientes_activos", "Clientes activos",
            "COUNT(DISTINCT c.cliente_id) FILTER (WHERE v.cliente_sk > 0)", "no aditiva", "entero",
            "COUNT(DISTINCT cliente_id) excluyendo miembros desconocidos", ("cliente_sk",),
            "analizar_clientes", ("c",)),
]}


@dataclass(frozen=True)
class Dimension:
    codigo: str
    nombre: str
    alias: str                  # alias de la tabla de dimensión
    columna: str                # columna mostrada / agrupada (lista blanca)
    temporal: bool = False
    orden_columna: str | None = None   # columna para orden cronológico
    jerarquia: str = ""
    intencion: str = "analizar_ventas"
    sql: str | None = None             # expresión calculada (lista blanca) cuando no es una columna simple

    @property
    def expresion(self) -> str:
        return self.sql or f"{self.alias}.{self.columna}"

    @property
    def tabla(self) -> str:
        return TABLA_POR_ALIAS[self.alias]


DIMENSIONES: dict[str, Dimension] = {d.codigo: d for d in [
    Dimension("anio", "Año", "f", "anio", True, "anio", "Tiempo: día → mes → trimestre → año", "analizar_tendencia"),
    Dimension("semestre", "Semestre", "f", "semestre", True, "semestre", "Tiempo", "analizar_tendencia"),
    Dimension("trimestre", "Trimestre", "f", "anio_trimestre", True, "anio_trimestre", "Tiempo", "analizar_tendencia"),
    Dimension("mes", "Mes", "f", "anio_mes", True, "anio_mes", "Tiempo", "analizar_tendencia"),
    Dimension("dia_semana", "Día de la semana", "f", "nombre_dia", False, "dia_semana_iso", "Tiempo", "analizar_tendencia"),
    Dimension("tipo_dia", "Tipo de día", "f", "es_fin_de_semana", intencion="analizar_tendencia",
              sql="CASE WHEN f.es_fin_de_semana THEN 'Fin de semana' ELSE 'Entre semana' END"),
    Dimension("categoria", "Categoría", "p", "categoria", jerarquia="Producto: producto → subcategoría → categoría",
              intencion="analizar_productos"),
    Dimension("subcategoria", "Subcategoría", "p", "subcategoria", intencion="analizar_productos"),
    Dimension("producto", "Producto", "p", "nombre", intencion="analizar_productos"),
    Dimension("marca", "Marca", "p", "marca", intencion="analizar_productos"),
    # El nombre NO identifica al cliente (hay razones sociales repetidas): se agrupa por nombre + clave natural
    Dimension("cliente", "Cliente", "c", "nombre", intencion="analizar_clientes",
              sql="c.nombre || ' (' || c.cliente_id || ')'"),
    Dimension("segmento", "Segmento de cliente", "c", "segmento", jerarquia="Cliente (SCD2): versión → segmento",
              intencion="analizar_clientes"),
    Dimension("tipo_cliente", "Tipo de cliente", "c", "tipo_cliente", intencion="analizar_clientes"),
    Dimension("ciudad_cliente", "Ciudad del cliente", "c", "ciudad", intencion="analizar_clientes"),
    Dimension("sucursal", "Sucursal", "s", "nombre", jerarquia="Geografía: sucursal → ciudad → estado → región",
              intencion="analizar_sucursales"),
    Dimension("ciudad", "Ciudad de la sucursal", "s", "ciudad", intencion="analizar_sucursales"),
    Dimension("estado", "Estado", "s", "estado", intencion="analizar_sucursales"),
    Dimension("region", "Región", "s", "region", intencion="analizar_sucursales"),
    Dimension("canal", "Canal", "n", "nombre", jerarquia="Canal → tipo de canal", intencion="analizar_canales"),
    Dimension("tipo_canal", "Tipo de canal", "n", "tipo_canal", intencion="analizar_canales"),
]}

DIMENSIONES_TEMPORALES = {c for c, d in DIMENSIONES.items() if d.temporal}

# Dimensiones cuyos valores se pueden usar como filtro (se cargan del Data Mart al iniciar)
DIMENSIONES_FILTRABLES = ["categoria", "subcategoria", "producto", "marca", "segmento", "tipo_cliente",
                          "sucursal", "ciudad", "estado", "region", "canal", "tipo_canal", "cliente", "tipo_dia"]

# Conceptos que NO existen en el Data Mart (para reconocer límites y no inventar)
DIMENSIONES_NO_DISPONIBLES = {
    "vendedor": "vendedor", "vendedores": "vendedor", "empleado": "empleado", "empleados": "empleado",
    "cajero": "cajero", "cajeros": "cajero", "proveedor": "proveedor", "proveedores": "proveedor",
    "metodo de pago": "método de pago", "metodos de pago": "método de pago", "forma de pago": "forma de pago",
    "formas de pago": "forma de pago", "color": "color", "talla": "talla", "departamento": "departamento",
    "almacen": "almacén", "bodega": "bodega", "repartidor": "repartidor", "campana": "campaña",
    "promocion": "promoción", "cupon": "cupón", "hora": "hora del día", "turno": "turno", "edad": "edad",
    "genero": "género", "sexo": "sexo", "pais": "país", "moneda": "moneda", "lote": "lote",
}

TEMAS_FUERA_DE_ALCANCE = [
    "inventario", "existencia", "existencias", "stock", "nomina", "salario", "salarios", "sueldo", "sueldos",
    "clima", "tasa de cambio", "dolar bcv", "tasa bcv", "devolucion", "devoluciones", "presupuesto", "meta de venta",
    "metas", "competencia", "competidores", "satisfaccion", "encuesta", "publicidad", "redes sociales",
    "impuesto", "iva", "deuda", "cuentas por cobrar", "cuentas por pagar", "flujo de caja", "empleados",
    "contratacion", "rotacion de personal", "precio de la accion", "bolsa", "noticias", "receta", "chiste",
    "capital de", "presidente", "pronostico del tiempo", "futbol", "partido",
    # proyecciones (el Data Mart sólo tiene historia)
    "proyeccion", "proyecciones", "proyectar", "pronostico", "pronosticos", "prediccion", "predecir", "forecast",
    "proximo mes", "proximo trimestre", "proximo semestre", "proximo ano", "siguiente mes", "siguiente trimestre",
    "siguiente ano", "el ano que viene", "venderemos", "vamos a vender",
    # hechos que no están en el Data Mart
    "anulado", "anulados", "anulada", "anuladas", "anulacion", "anulaciones", "cancelado", "cancelados",
    "clientes nuevos", "nuevos clientes", "captacion", "fecha de registro", "rentabilidad por empleado",
]

INTENCIONES = {
    "analizar_ventas": "Analizar ventas e ingresos",
    "analizar_rentabilidad": "Analizar rentabilidad (margen, costo, descuento)",
    "analizar_clientes": "Analizar clientes y segmentos",
    "analizar_productos": "Analizar productos y categorías",
    "analizar_canales": "Analizar canales de venta",
    "analizar_sucursales": "Analizar sucursales y geografía",
    "analizar_tendencia": "Analizar tendencia temporal",
    "comparar_desempeno": "Comparar periodos o miembros",
}

OPERACIONES = {
    "total": "Agregado total",
    "ranking": "Ranking ordenado",
    "tendencia": "Serie temporal",
    "comparacion_periodos": "Comparación entre dos periodos (variación)",
    "comparacion_miembros": "Comparación entre miembros de una dimensión",
}

# Criterios ofrecidos cuando la pregunta es ambigua ("¿cuál fue el mejor canal?")
CRITERIOS_AMBIGUEDAD = ["ingreso_neto", "margen_bruto", "unidades", "ticket_promedio"]


@dataclass(frozen=True)
class FuenteDef:
    tabla: str
    tipo: str
    campos: tuple = field(default_factory=tuple)
    descripcion: str = ""


FUENTES = [
    FuenteDef("dm.fact_ventas", "hecho",
              ("numero_ticket", "linea_ticket", "fecha_sk", "producto_sk", "cliente_sk", "sucursal_sk", "canal_sk",
               "cantidad", "precio_unitario", "monto_bruto", "descuento", "ingreso_neto", "costo_total", "margen_bruto"),
              "Hecho de ventas. Grano: una línea de producto de un ticket completado."),
    FuenteDef("dm.dim_fecha", "dimension", ("fecha_sk", "fecha", "anio_mes", "anio_trimestre", "anio", "nombre_dia"),
              "Calendario. Jerarquía día → mes → trimestre → semestre → año."),
    FuenteDef("dm.dim_producto", "dimension", ("producto_sk", "producto_id", "nombre", "marca", "subcategoria", "categoria"),
              "Productos (SCD1). Jerarquía producto → subcategoría → categoría."),
    FuenteDef("dm.dim_cliente", "dimension", ("cliente_sk", "cliente_id", "nombre", "segmento", "tipo_cliente",
                                              "fecha_inicio", "fecha_fin", "es_actual"),
              "Clientes con historia de segmento (SCD Tipo 2)."),
    FuenteDef("dm.dim_sucursal", "dimension", ("sucursal_sk", "sucursal_id", "nombre", "ciudad", "estado", "region"),
              "Sucursales. Jerarquía sucursal → ciudad → estado → región."),
    FuenteDef("dm.dim_canal", "dimension", ("canal_sk", "canal_id", "nombre", "tipo_canal"),
              "Canales de venta. Jerarquía canal → tipo de canal."),
]


def describir_capacidades() -> str:
    mets = ", ".join(m.nombre.lower() for m in METRICAS.values())
    dims = ", ".join(d.nombre.lower() for d in DIMENSIONES.values())
    return f"Métricas disponibles: {mets}. Dimensiones disponibles: {dims}."
