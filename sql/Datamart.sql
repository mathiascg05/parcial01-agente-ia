/* =====================================================================================
   PARCIAL 01 - Tópicos Especiales para la Gestión de Datos (Prof. Armen Djenanian)
   Data Mart de Ventas - Distribuidora Ávila C.A. (empresa ficticia)
   Motor: PostgreSQL 14+   |   Metodología: Kimball (bottom-up), esquema estrella

   CONTENIDO
     §1  Esquemas: oltp (operacional) · dm (analítico) · control (auditoría ETL)
     §2  Tablas operacionales (réplica de la fuente, sin transformar)
     §3  Carga de la fuente (CSV)  -> \copy
     §4  Modelo dimensional: dimensiones, hecho, claves, restricciones, índices
     §5  ETL: transformación y carga del Data Mart
     §6  Rol de solo lectura para el agente
     §7  Controles de integridad y conciliación (vistas control.*)
     §8  Consultas analíticas parametrizadas usadas por el agente (PREPARE / EXECUTE)

   EJECUCIÓN REPRODUCIBLE (desde la raíz del proyecto, para que las rutas de \copy funcionen):
       createdb parcial01
       psql -d parcial01 -v ON_ERROR_STOP=1 -f sql/Datamart.sql
     o bien, sin psql:   python scripts/setup_datamart.py   (lee .env, hace lo mismo y concilia)

   El script es idempotente: borra y recrea los esquemas oltp, dm y control.
   ===================================================================================== */

SET client_min_messages = warning;

/* =====================================================================================
   §1  ESQUEMAS
   - oltp    : datos OPERACIONALES tal como llegan del POS/CRM (normalizados, con errores
               de calidad, orientados a registrar transacciones, se actualizan).
   - dm      : datos ANALÍTICOS (esquema estrella, históricos, no volátiles, limpios,
               orientados a consulta). Es la ÚNICA fuente que consulta el agente.
   - control : bitácora de cargas, rechazos y vistas de conciliación/integridad.
   ===================================================================================== */
DROP SCHEMA IF EXISTS dm CASCADE;
DROP SCHEMA IF EXISTS control CASCADE;
DROP SCHEMA IF EXISTS oltp CASCADE;
CREATE SCHEMA oltp;
CREATE SCHEMA dm;
CREATE SCHEMA control;

/* =====================================================================================
   §2  TABLAS OPERACIONALES (fuente)
   Reproducen la estructura del sistema transaccional. Intencionalmente NO tienen todas
   las restricciones: la fuente real trae duplicados y claves huérfanas que el ETL debe tratar.
   ===================================================================================== */
CREATE TABLE oltp.sucursal (
    sucursal_id     VARCHAR(5)   PRIMARY KEY,
    nombre          VARCHAR(60)  NOT NULL,
    ciudad          VARCHAR(60),
    estado          VARCHAR(60),
    region          VARCHAR(40),
    fecha_apertura  DATE
);

CREATE TABLE oltp.canal (
    canal_id    VARCHAR(5)  PRIMARY KEY,
    nombre      VARCHAR(40) NOT NULL,
    tipo_canal  VARCHAR(20)
);

CREATE TABLE oltp.producto (
    producto_id        VARCHAR(6)    PRIMARY KEY,
    sku                VARCHAR(12),
    nombre             VARCHAR(120)  NOT NULL,
    categoria          VARCHAR(40),
    subcategoria       VARCHAR(40),
    marca              VARCHAR(40),
    precio_lista       NUMERIC(12,2),
    costo_estandar     NUMERIC(12,2),
    fecha_lanzamiento  DATE,
    activo             CHAR(1)
);

CREATE TABLE oltp.cliente (
    cliente_id       VARCHAR(7)   PRIMARY KEY,
    nombre           VARCHAR(120) NOT NULL,
    documento        VARCHAR(20),
    tipo_cliente     VARCHAR(10),
    ciudad           VARCHAR(60),
    fecha_registro   DATE,
    segmento_actual  VARCHAR(20)          -- el CRM sólo guarda el valor vigente (sobrescribe)
);

-- Bitácora del CRM con cada reclasificación de segmento (fuente del SCD Tipo 2)
CREATE TABLE oltp.cliente_segmento_historial (
    cliente_id   VARCHAR(7)  NOT NULL REFERENCES oltp.cliente(cliente_id),
    segmento     VARCHAR(20) NOT NULL,
    fecha_desde  DATE        NOT NULL,
    fecha_hasta  DATE,                    -- NULL = vigente
    PRIMARY KEY (cliente_id, fecha_desde)
);

CREATE TABLE oltp.ticket (
    ticket_id    VARCHAR(10) PRIMARY KEY,
    fecha_hora   TIMESTAMP   NOT NULL,
    sucursal_id  VARCHAR(5)  NOT NULL,
    canal_id     VARCHAR(5)  NOT NULL,
    cliente_id   VARCHAR(7),              -- puede venir vacío (consumidor final) o huérfano
    estado       VARCHAR(12) NOT NULL,    -- COMPLETADO | ANULADO
    metodo_pago  VARCHAR(20)
);

CREATE TABLE oltp.ticket_detalle (
    detalle_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- id técnico de la réplica
    ticket_id        VARCHAR(10)   NOT NULL,
    linea            SMALLINT      NOT NULL,
    producto_id      VARCHAR(6),
    cantidad         INTEGER,
    precio_unitario  NUMERIC(12,2),
    descuento        NUMERIC(12,2),
    costo_unitario   NUMERIC(12,2)
    -- SIN UNIQUE(ticket_id, linea): la fuente trae duplicados por re-sincronización del POS
);

/* =====================================================================================
   §3  CARGA DE LA FUENTE
   Archivos generados por data/generar_dataset.py (determinista, semilla fija).
   ===================================================================================== */
\copy oltp.sucursal FROM 'data/fuente/sucursales.csv' WITH (FORMAT csv, HEADER true)
\copy oltp.canal FROM 'data/fuente/canales.csv' WITH (FORMAT csv, HEADER true)
\copy oltp.producto FROM 'data/fuente/productos.csv' WITH (FORMAT csv, HEADER true)
\copy oltp.cliente FROM 'data/fuente/clientes.csv' WITH (FORMAT csv, HEADER true)
\copy oltp.cliente_segmento_historial FROM 'data/fuente/cliente_segmento_historial.csv' WITH (FORMAT csv, HEADER true)
\copy oltp.ticket FROM 'data/fuente/tickets.csv' WITH (FORMAT csv, HEADER true)
\copy oltp.ticket_detalle (ticket_id, linea, producto_id, cantidad, precio_unitario, descuento, costo_unitario) FROM 'data/fuente/ticket_detalle.csv' WITH (FORMAT csv, HEADER true)

-- En CSV, los vacíos de texto llegan como '' : se normalizan a NULL en la réplica
UPDATE oltp.ticket   SET cliente_id   = NULL WHERE cliente_id   = '';
UPDATE oltp.producto SET subcategoria = NULL WHERE subcategoria = '';
UPDATE oltp.cliente  SET ciudad       = NULL WHERE ciudad       = '';

/* =====================================================================================
   §4  MODELO DIMENSIONAL (esquema estrella)

   PROCESO DE NEGOCIO: ventas (tickets de venta completados).
   GRANO DE dm.fact_ventas (una oración):
     "Una fila por cada línea de producto de un ticket de venta completado, es decir, un
      producto vendido en un ticket, en una fecha, sucursal y canal, a un cliente."

   CLAVES SUSTITUTAS (_sk): enteros sin significado de negocio generados por el DW. Sirven para
   (a) aislar el DW de cambios/reutilización de códigos en la fuente, (b) permitir varias
   versiones de un mismo cliente (SCD2), (c) representar miembros desconocidos (-1, -2) y
   (d) joins más compactos y rápidos que con códigos alfanuméricos.

   MIEMBROS ESPECIALES en cada dimensión:
     -1 = 'No informado'        : la fuente trae la clave vacía/NULL.
     -2 = 'Sin correspondencia' : la fuente trae una clave que no existe en el maestro.
   Así ninguna venta se pierde (no se descartan ingresos) y la excepción queda visible.
   ===================================================================================== */

-- ---------------------------------------------------------------- dim_fecha ----------
-- Jerarquía: día -> mes -> trimestre -> semestre -> año
CREATE TABLE dm.dim_fecha (
    fecha_sk          INTEGER     PRIMARY KEY,          -- AAAAMMDD (clave inteligente estándar de fecha)
    fecha             DATE        NOT NULL UNIQUE,
    dia               SMALLINT    NOT NULL,
    nombre_dia        VARCHAR(10) NOT NULL,
    dia_semana_iso    SMALLINT    NOT NULL,             -- 1 = lunes ... 7 = domingo
    es_fin_de_semana  BOOLEAN     NOT NULL,
    semana_iso        SMALLINT    NOT NULL,
    mes               SMALLINT    NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nombre_mes        VARCHAR(10) NOT NULL,
    anio_mes          CHAR(7)     NOT NULL,             -- '2026-07'
    trimestre         SMALLINT    NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    anio_trimestre    CHAR(7)     NOT NULL,             -- '2026-T3'
    semestre          SMALLINT    NOT NULL,
    anio              SMALLINT    NOT NULL
);

-- ---------------------------------------------------------------- dim_producto -------
-- SCD Tipo 1 (se sobrescribe). Jerarquía: producto -> subcategoría -> categoría
CREATE TABLE dm.dim_producto (
    producto_sk         INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    producto_id         VARCHAR(6)   NOT NULL UNIQUE,   -- clave natural (negocio)
    sku                 VARCHAR(12)  NOT NULL,
    nombre              VARCHAR(120) NOT NULL,
    marca               VARCHAR(40)  NOT NULL,
    subcategoria        VARCHAR(40)  NOT NULL,
    categoria           VARCHAR(40)  NOT NULL,
    precio_lista_actual NUMERIC(12,2)
);

-- ---------------------------------------------------------------- dim_cliente --------
-- SCD Tipo 2 sobre 'segmento' (se conserva la historia: una fila por versión).
-- Atributos nombre/ciudad se tratan como Tipo 1 (se corrigen en todas las versiones).
CREATE TABLE dm.dim_cliente (
    cliente_sk     INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    cliente_id     VARCHAR(7)   NOT NULL,               -- clave natural (se repite entre versiones)
    nombre         VARCHAR(120) NOT NULL,
    tipo_cliente   VARCHAR(20)  NOT NULL,
    ciudad         VARCHAR(60)  NOT NULL,
    segmento       VARCHAR(20)  NOT NULL,
    fecha_inicio   DATE         NOT NULL,               -- vigencia de la versión
    fecha_fin      DATE         NOT NULL,               -- 9999-12-31 = vigente
    es_actual      BOOLEAN      NOT NULL,
    version        SMALLINT     NOT NULL,
    CONSTRAINT uq_cliente_version UNIQUE (cliente_id, fecha_inicio),
    CONSTRAINT ck_cliente_vigencia CHECK (fecha_inicio <= fecha_fin)
);

-- ---------------------------------------------------------------- dim_sucursal -------
-- Jerarquía geográfica: sucursal -> ciudad -> estado -> región
CREATE TABLE dm.dim_sucursal (
    sucursal_sk     INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sucursal_id     VARCHAR(5)  NOT NULL UNIQUE,
    nombre          VARCHAR(60) NOT NULL,
    ciudad          VARCHAR(60) NOT NULL,
    estado          VARCHAR(60) NOT NULL,
    region          VARCHAR(40) NOT NULL,
    fecha_apertura  DATE
);

-- ---------------------------------------------------------------- dim_canal ----------
-- Jerarquía: canal -> tipo de canal
CREATE TABLE dm.dim_canal (
    canal_sk    INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    canal_id    VARCHAR(5)  NOT NULL UNIQUE,
    nombre      VARCHAR(40) NOT NULL,
    tipo_canal  VARCHAR(20) NOT NULL
);

-- ---------------------------------------------------------------- fact_ventas --------
/* MÉTRICAS
   Aditivas (se suman por cualquier dimensión): cantidad, monto_bruto, descuento,
       ingreso_neto, costo_total, margen_bruto.
   Semiaditivas: este hecho es TRANSACCIONAL, por lo que no almacena saldos; no hay métricas
       semiaditivas. Ejemplo de lo que sería una: existencias de inventario o saldo por cobrar
       (sumables por producto/sucursal pero NO a lo largo del tiempo). Se documenta en el informe.
   No aditivas (se recalculan a partir de sumas, nunca se suman ni se promedian):
       precio_unitario (atributo de la línea), margen_% = SUM(margen)/SUM(ingreso_neto),
       ticket_promedio = SUM(ingreso_neto)/COUNT(DISTINCT numero_ticket),
       % descuento = SUM(descuento)/SUM(monto_bruto), clientes activos (COUNT DISTINCT).
   numero_ticket es una DIMENSIÓN DEGENERADA: permite contar transacciones sin duplicar
   (COUNT DISTINCT) y rastrear cada fila hasta la fuente. */
CREATE TABLE dm.fact_ventas (
    numero_ticket    VARCHAR(10)   NOT NULL,            -- dimensión degenerada
    linea_ticket     SMALLINT      NOT NULL,
    fecha_sk         INTEGER       NOT NULL REFERENCES dm.dim_fecha(fecha_sk),
    producto_sk      INTEGER       NOT NULL REFERENCES dm.dim_producto(producto_sk),
    cliente_sk       INTEGER       NOT NULL REFERENCES dm.dim_cliente(cliente_sk),
    sucursal_sk      INTEGER       NOT NULL REFERENCES dm.dim_sucursal(sucursal_sk),
    canal_sk         INTEGER       NOT NULL REFERENCES dm.dim_canal(canal_sk),
    cantidad         INTEGER       NOT NULL CHECK (cantidad > 0),
    precio_unitario  NUMERIC(12,2) NOT NULL CHECK (precio_unitario >= 0),
    monto_bruto      NUMERIC(14,2) NOT NULL,
    descuento        NUMERIC(14,2) NOT NULL CHECK (descuento >= 0),
    ingreso_neto     NUMERIC(14,2) NOT NULL,
    costo_total      NUMERIC(14,2) NOT NULL CHECK (costo_total >= 0),
    margen_bruto     NUMERIC(14,2) NOT NULL,
    lote_id          INTEGER       NOT NULL,
    CONSTRAINT pk_fact_ventas PRIMARY KEY (numero_ticket, linea_ticket),   -- evita duplicidad del grano
    CONSTRAINT ck_monto_bruto  CHECK (monto_bruto  = cantidad * precio_unitario),
    CONSTRAINT ck_ingreso_neto CHECK (ingreso_neto = monto_bruto - descuento),
    CONSTRAINT ck_margen       CHECK (margen_bruto = ingreso_neto - costo_total),
    CONSTRAINT ck_descuento    CHECK (descuento <= monto_bruto)
);

CREATE INDEX ix_fv_fecha    ON dm.fact_ventas (fecha_sk);
CREATE INDEX ix_fv_producto ON dm.fact_ventas (producto_sk);
CREATE INDEX ix_fv_cliente  ON dm.fact_ventas (cliente_sk);
CREATE INDEX ix_fv_sucursal ON dm.fact_ventas (sucursal_sk);
CREATE INDEX ix_fv_canal    ON dm.fact_ventas (canal_sk);

-- ---------------------------------------------------------------- control ------------
CREATE TABLE control.etl_lote (
    lote_id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inicio         TIMESTAMP NOT NULL DEFAULT clock_timestamp(),
    fin            TIMESTAMP,
    descripcion    TEXT
);

CREATE TABLE control.etl_rechazo (
    rechazo_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lote_id        INTEGER NOT NULL REFERENCES control.etl_lote(lote_id),
    origen         VARCHAR(40) NOT NULL,
    clave_origen   VARCHAR(40) NOT NULL,
    motivo         VARCHAR(40) NOT NULL,     -- TICKET_ANULADO | LINEA_DUPLICADA | CANTIDAD_INVALIDA
    detalle        TEXT
);

/* =====================================================================================
   §5  ETL (Extract-Transform-Load) oltp -> dm
   ===================================================================================== */
INSERT INTO control.etl_lote (descripcion) VALUES ('Carga inicial completa del Data Mart de Ventas');

-- 5.1 dim_fecha: calendario continuo 2024-01-01 .. 2026-12-31 (incluye días sin ventas)
INSERT INTO dm.dim_fecha
SELECT  TO_CHAR(d, 'YYYYMMDD')::INT,
        d,
        EXTRACT(DAY FROM d),
        (ARRAY['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'])[EXTRACT(ISODOW FROM d)],
        EXTRACT(ISODOW FROM d),
        EXTRACT(ISODOW FROM d) IN (6, 7),
        EXTRACT(WEEK FROM d),
        EXTRACT(MONTH FROM d),
        (ARRAY['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre',
               'Octubre','Noviembre','Diciembre'])[EXTRACT(MONTH FROM d)],
        TO_CHAR(d, 'YYYY-MM'),
        EXTRACT(QUARTER FROM d),
        TO_CHAR(d, 'YYYY') || '-T' || EXTRACT(QUARTER FROM d),
        CASE WHEN EXTRACT(MONTH FROM d) <= 6 THEN 1 ELSE 2 END,
        EXTRACT(YEAR FROM d)
FROM generate_series(DATE '2024-01-01', DATE '2026-12-31', INTERVAL '1 day') AS g(d);

-- Miembro desconocido de fecha (no debería usarse: fecha_hora es obligatoria en la fuente)
INSERT INTO dm.dim_fecha VALUES (-1, DATE '1900-01-01', 1, 'N/D', 1, FALSE, 1, 1, 'N/D', 'N/D', 1, 'N/D', 1, 1900);

-- 5.2 Miembros especiales en las demás dimensiones
INSERT INTO dm.dim_producto (producto_sk, producto_id, sku, nombre, marca, subcategoria, categoria)
VALUES (-1, 'N/I', 'N/I', 'Producto no informado', 'No informado', 'No informado', 'No informado'),
       (-2, 'S/C', 'S/C', 'Producto sin correspondencia', 'Sin correspondencia', 'Sin correspondencia', 'Sin correspondencia');

INSERT INTO dm.dim_cliente (cliente_sk, cliente_id, nombre, tipo_cliente, ciudad, segmento, fecha_inicio, fecha_fin, es_actual, version)
VALUES (-1, 'N/I', 'Consumidor final (no informado)', 'No informado', 'No informada', 'No informado', DATE '1900-01-01', DATE '9999-12-31', TRUE, 1),
       (-2, 'S/C', 'Cliente sin correspondencia', 'Sin correspondencia', 'Sin correspondencia', 'Sin correspondencia', DATE '1900-01-01', DATE '9999-12-31', TRUE, 1);

INSERT INTO dm.dim_sucursal (sucursal_sk, sucursal_id, nombre, ciudad, estado, region)
VALUES (-1, 'N/I', 'Sucursal no informada', 'No informada', 'No informado', 'No informada'),
       (-2, 'S/C', 'Sucursal sin correspondencia', 'Sin correspondencia', 'Sin correspondencia', 'Sin correspondencia');

INSERT INTO dm.dim_canal (canal_sk, canal_id, nombre, tipo_canal)
VALUES (-1, 'N/I', 'Canal no informado', 'No informado'),
       (-2, 'S/C', 'Canal sin correspondencia', 'Sin correspondencia');

-- 5.3 Dimensiones (tratamiento de valores faltantes con COALESCE)
INSERT INTO dm.dim_producto (producto_id, sku, nombre, marca, subcategoria, categoria, precio_lista_actual)
SELECT producto_id, COALESCE(sku, 'N/D'), nombre, COALESCE(marca, 'Sin marca'),
       COALESCE(subcategoria, 'Sin subcategoría'), COALESCE(categoria, 'Sin categoría'), precio_lista
FROM oltp.producto ORDER BY producto_id;

INSERT INTO dm.dim_sucursal (sucursal_id, nombre, ciudad, estado, region, fecha_apertura)
SELECT sucursal_id, nombre, COALESCE(ciudad, 'No informada'), COALESCE(estado, 'No informado'),
       COALESCE(region, 'No informada'), fecha_apertura
FROM oltp.sucursal ORDER BY sucursal_id;

INSERT INTO dm.dim_canal (canal_id, nombre, tipo_canal)
SELECT canal_id, nombre, COALESCE(tipo_canal, 'No informado') FROM oltp.canal ORDER BY canal_id;

-- 5.4 dim_cliente SCD Tipo 2: una versión por cada tramo del historial de segmento
INSERT INTO dm.dim_cliente (cliente_id, nombre, tipo_cliente, ciudad, segmento, fecha_inicio, fecha_fin, es_actual, version)
SELECT c.cliente_id, c.nombre, COALESCE(c.tipo_cliente, 'No informado'), COALESCE(c.ciudad, 'No informada'),
       h.segmento, h.fecha_desde, COALESCE(h.fecha_hasta, DATE '9999-12-31'),
       h.fecha_hasta IS NULL,
       ROW_NUMBER() OVER (PARTITION BY c.cliente_id ORDER BY h.fecha_desde)
FROM oltp.cliente c
JOIN oltp.cliente_segmento_historial h ON h.cliente_id = c.cliente_id
ORDER BY c.cliente_id, h.fecha_desde;

-- 5.5 Registro de rechazos (excepciones documentadas)
INSERT INTO control.etl_rechazo (lote_id, origen, clave_origen, motivo, detalle)
SELECT 1, 'oltp.ticket', t.ticket_id, 'TICKET_ANULADO', 'Ticket anulado: no constituye venta'
FROM oltp.ticket t WHERE t.estado <> 'COMPLETADO';

INSERT INTO control.etl_rechazo (lote_id, origen, clave_origen, motivo, detalle)
SELECT 1, 'oltp.ticket_detalle', d.ticket_id || '#' || d.linea, 'LINEA_DUPLICADA',
       'detalle_id ' || d.detalle_id || ' repite (ticket, línea) ya cargado'
FROM (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY ticket_id, linea ORDER BY detalle_id) AS rn
      FROM oltp.ticket_detalle d) d
WHERE d.rn > 1;

INSERT INTO control.etl_rechazo (lote_id, origen, clave_origen, motivo, detalle)
SELECT 1, 'oltp.ticket_detalle', d.ticket_id || '#' || d.linea, 'CANTIDAD_INVALIDA',
       'cantidad = ' || COALESCE(d.cantidad::TEXT, 'NULL')
FROM oltp.ticket_detalle d
JOIN oltp.ticket t ON t.ticket_id = d.ticket_id AND t.estado = 'COMPLETADO'
WHERE COALESCE(d.cantidad, 0) <= 0
  AND d.detalle_id IN (SELECT MIN(detalle_id) FROM oltp.ticket_detalle GROUP BY ticket_id, linea);

-- 5.6 Vista de staging: líneas VÁLIDAS de la fuente (deduplicadas, completadas, cantidad > 0).
--     Se usa para cargar el hecho Y para conciliar (misma definición de "venta válida").
CREATE VIEW control.v_fuente_valida AS
SELECT d.ticket_id, d.linea, d.producto_id, d.cantidad, d.precio_unitario,
       COALESCE(d.descuento, 0) AS descuento, d.costo_unitario,
       t.fecha_hora, t.sucursal_id, t.canal_id, t.cliente_id
FROM (SELECT d.*, ROW_NUMBER() OVER (PARTITION BY ticket_id, linea ORDER BY detalle_id) AS rn
      FROM oltp.ticket_detalle d) d
JOIN oltp.ticket t ON t.ticket_id = d.ticket_id
WHERE d.rn = 1
  AND t.estado = 'COMPLETADO'
  AND d.cantidad > 0;

-- 5.7 Hecho: búsqueda de claves sustitutas (lookup) con miembros -1 / -2
INSERT INTO dm.fact_ventas (numero_ticket, linea_ticket, fecha_sk, producto_sk, cliente_sk, sucursal_sk,
                            canal_sk, cantidad, precio_unitario, monto_bruto, descuento, ingreso_neto,
                            costo_total, margen_bruto, lote_id)
SELECT f.ticket_id,
       f.linea,
       COALESCE(df.fecha_sk, -1),
       CASE WHEN f.producto_id IS NULL THEN -1 ELSE COALESCE(dp.producto_sk, -2) END,
       CASE WHEN f.cliente_id  IS NULL THEN -1 ELSE COALESCE(dc.cliente_sk,  -2) END,
       CASE WHEN f.sucursal_id IS NULL THEN -1 ELSE COALESCE(ds.sucursal_sk, -2) END,
       CASE WHEN f.canal_id    IS NULL THEN -1 ELSE COALESCE(dn.canal_sk,    -2) END,
       f.cantidad,
       f.precio_unitario,
       f.cantidad * f.precio_unitario,                                        -- monto bruto
       f.descuento,
       f.cantidad * f.precio_unitario - f.descuento,                          -- ingreso neto
       f.cantidad * f.costo_unitario,                                         -- costo total
       (f.cantidad * f.precio_unitario - f.descuento) - f.cantidad * f.costo_unitario,  -- margen bruto
       1
FROM control.v_fuente_valida f
LEFT JOIN dm.dim_fecha    df ON df.fecha = f.fecha_hora::DATE
LEFT JOIN dm.dim_producto dp ON dp.producto_id = f.producto_id
LEFT JOIN dm.dim_cliente  dc ON dc.cliente_id  = f.cliente_id                -- SCD2: versión vigente
                            AND f.fecha_hora::DATE BETWEEN dc.fecha_inicio AND dc.fecha_fin
LEFT JOIN dm.dim_sucursal ds ON ds.sucursal_id = f.sucursal_id
LEFT JOIN dm.dim_canal    dn ON dn.canal_id    = f.canal_id;

UPDATE control.etl_lote SET fin = clock_timestamp() WHERE lote_id = 1;

ANALYZE dm.fact_ventas;

/* =====================================================================================
   §6  ROL DE SOLO LECTURA PARA EL AGENTE (defensa en profundidad)
   El agente se conecta con este rol: sólo SELECT sobre el esquema dm, transacciones de
   solo lectura forzadas y tiempo máximo por consulta. No ve oltp ni control.
   La contraseña NO se guarda aquí: se define localmente (scripts/setup_datamart.py la toma
   de .env) o manualmente con:  ALTER ROLE agente_lector PASSWORD '...';
   ===================================================================================== */
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agente_lector') THEN
        CREATE ROLE agente_lector LOGIN;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO agente_lector', current_database());
END $$;

ALTER ROLE agente_lector SET default_transaction_read_only = on;
ALTER ROLE agente_lector SET statement_timeout = '5s';
ALTER ROLE agente_lector SET search_path = dm;
REVOKE ALL ON SCHEMA oltp, control FROM agente_lector;
REVOKE ALL ON ALL TABLES IN SCHEMA oltp, control FROM agente_lector;
GRANT USAGE ON SCHEMA dm TO agente_lector;
GRANT SELECT ON ALL TABLES IN SCHEMA dm TO agente_lector;

/* =====================================================================================
   §7  CONTROLES DE INTEGRIDAD Y CONCILIACIÓN
   Resultado esperado: estado = 'OK' en todas las filas.
   ===================================================================================== */

-- 7.1 Conciliación Data Mart vs fuente (operacional)
CREATE VIEW control.v_conciliacion AS
WITH fuente AS (
    SELECT COUNT(*)                                        AS lineas,
           COUNT(DISTINCT ticket_id)                       AS tickets,
           SUM(cantidad)                                   AS unidades,
           SUM(cantidad * precio_unitario - descuento)     AS ingreso_neto,
           SUM(cantidad * costo_unitario)                  AS costo
    FROM control.v_fuente_valida
), dm AS (
    SELECT COUNT(*) AS lineas, COUNT(DISTINCT numero_ticket) AS tickets, SUM(cantidad) AS unidades,
           SUM(ingreso_neto) AS ingreso_neto, SUM(costo_total) AS costo
    FROM dm.fact_ventas
), cuadre AS (
    SELECT (SELECT COUNT(*) FROM oltp.ticket_detalle)                                   AS lineas_crudas,
           (SELECT COUNT(*) FROM oltp.ticket_detalle d JOIN oltp.ticket t USING (ticket_id)
             WHERE t.estado <> 'COMPLETADO')                                            AS lineas_anuladas,
           (SELECT COUNT(*) FROM control.etl_rechazo r
             WHERE r.motivo = 'LINEA_DUPLICADA'
               AND split_part(r.clave_origen, '#', 1) IN
                   (SELECT ticket_id FROM oltp.ticket WHERE estado = 'COMPLETADO'))     AS duplicadas,
           (SELECT COUNT(*) FROM control.etl_rechazo WHERE motivo = 'CANTIDAD_INVALIDA') AS invalidas
), mensual AS (
    SELECT COUNT(*) AS meses_con_diferencia
    FROM (SELECT TO_CHAR(fecha_hora, 'YYYY-MM') AS mes, SUM(cantidad * precio_unitario - descuento) AS v
          FROM control.v_fuente_valida GROUP BY 1) a
    FULL JOIN (SELECT f.anio_mes AS mes, SUM(v.ingreso_neto) AS v
               FROM dm.fact_ventas v JOIN dm.dim_fecha f USING (fecha_sk) GROUP BY 1) b USING (mes)
    WHERE COALESCE(a.v, 0) <> COALESCE(b.v, 0)
)
SELECT 'C1 Líneas válidas'            AS control, f.lineas::NUMERIC AS valor_fuente, d.lineas::NUMERIC AS valor_dm,
       (d.lineas - f.lineas)::NUMERIC AS diferencia FROM fuente f, dm d
UNION ALL SELECT 'C2 Tickets (transacciones)', f.tickets, d.tickets, d.tickets - f.tickets FROM fuente f, dm d
UNION ALL SELECT 'C3 Unidades vendidas',       f.unidades, d.unidades, d.unidades - f.unidades FROM fuente f, dm d
UNION ALL SELECT 'C4 Ingreso neto (USD)',      f.ingreso_neto, d.ingreso_neto, d.ingreso_neto - f.ingreso_neto FROM fuente f, dm d
UNION ALL SELECT 'C5 Costo total (USD)',       f.costo, d.costo, d.costo - f.costo FROM fuente f, dm d
UNION ALL SELECT 'C6 Cuadre de líneas: crudas = DM + anuladas + duplicadas + inválidas',
                 c.lineas_crudas, d.lineas + c.lineas_anuladas + c.duplicadas + c.invalidas,
                 d.lineas + c.lineas_anuladas + c.duplicadas + c.invalidas - c.lineas_crudas FROM cuadre c, dm d
UNION ALL SELECT 'C7 Meses con diferencia de ingreso fuente vs DM', 0, m.meses_con_diferencia, m.meses_con_diferencia FROM mensual m;

CREATE VIEW control.v_conciliacion_estado AS
SELECT control, valor_fuente, valor_dm, diferencia, CASE WHEN diferencia = 0 THEN 'OK' ELSE 'REVISAR' END AS estado
FROM control.v_conciliacion;

-- 7.2 Integridad referencial y reglas del modelo
CREATE VIEW control.v_integridad AS
SELECT 'I1 Hechos con fecha_sk inexistente' AS control,
       COUNT(*) AS hallazgos FROM dm.fact_ventas f LEFT JOIN dm.dim_fecha d USING (fecha_sk) WHERE d.fecha_sk IS NULL
UNION ALL SELECT 'I2 Hechos con producto_sk inexistente',
       COUNT(*) FROM dm.fact_ventas f LEFT JOIN dm.dim_producto d USING (producto_sk) WHERE d.producto_sk IS NULL
UNION ALL SELECT 'I3 Hechos con cliente_sk inexistente',
       COUNT(*) FROM dm.fact_ventas f LEFT JOIN dm.dim_cliente d USING (cliente_sk) WHERE d.cliente_sk IS NULL
UNION ALL SELECT 'I4 Hechos con sucursal_sk inexistente',
       COUNT(*) FROM dm.fact_ventas f LEFT JOIN dm.dim_sucursal d USING (sucursal_sk) WHERE d.sucursal_sk IS NULL
UNION ALL SELECT 'I5 Hechos con canal_sk inexistente',
       COUNT(*) FROM dm.fact_ventas f LEFT JOIN dm.dim_canal d USING (canal_sk) WHERE d.canal_sk IS NULL
UNION ALL SELECT 'I6 Grano duplicado (ticket, línea) en el hecho',
       COUNT(*) FROM (SELECT 1 FROM dm.fact_ventas GROUP BY numero_ticket, linea_ticket HAVING COUNT(*) > 1) x
UNION ALL SELECT 'I7 Clientes con != 1 versión actual (SCD2)',
       COUNT(*) FROM (SELECT cliente_id FROM dm.dim_cliente GROUP BY cliente_id HAVING SUM(es_actual::INT) <> 1) x
UNION ALL SELECT 'I8 Versiones de cliente solapadas (SCD2)',
       COUNT(*) FROM dm.dim_cliente a JOIN dm.dim_cliente b
         ON a.cliente_id = b.cliente_id AND a.cliente_sk < b.cliente_sk
        AND a.fecha_inicio <= b.fecha_fin AND b.fecha_inicio <= a.fecha_fin
UNION ALL SELECT 'I9 Hechos fuera de la vigencia de su versión de cliente',
       COUNT(*) FROM dm.fact_ventas f JOIN dm.dim_cliente c USING (cliente_sk) JOIN dm.dim_fecha d USING (fecha_sk)
        WHERE d.fecha NOT BETWEEN c.fecha_inicio AND c.fecha_fin
UNION ALL SELECT 'I10 Reglas de cálculo incumplidas (bruto, neto, margen)',
       COUNT(*) FROM dm.fact_ventas
        WHERE monto_bruto <> cantidad * precio_unitario OR ingreso_neto <> monto_bruto - descuento
           OR margen_bruto <> ingreso_neto - costo_total;

-- 7.3 Excepciones documentadas: hechos asignados a miembros especiales (no se pierden, se señalan)
CREATE VIEW control.v_excepciones AS
SELECT 'Cliente' AS dimension, c.nombre AS miembro, COUNT(*) AS lineas,
       COUNT(DISTINCT f.numero_ticket) AS tickets, SUM(f.ingreso_neto) AS ingreso_neto,
       ROUND(100.0 * SUM(f.ingreso_neto) / (SELECT SUM(ingreso_neto) FROM dm.fact_ventas), 3) AS pct_ingreso
FROM dm.fact_ventas f JOIN dm.dim_cliente c USING (cliente_sk) WHERE f.cliente_sk < 0 GROUP BY c.nombre
UNION ALL
SELECT 'Producto', p.nombre, COUNT(*), COUNT(DISTINCT f.numero_ticket), SUM(f.ingreso_neto),
       ROUND(100.0 * SUM(f.ingreso_neto) / (SELECT SUM(ingreso_neto) FROM dm.fact_ventas), 3)
FROM dm.fact_ventas f JOIN dm.dim_producto p USING (producto_sk) WHERE f.producto_sk < 0 GROUP BY p.nombre
UNION ALL
SELECT 'Rechazo ETL: ' || motivo, motivo, COUNT(*), NULL, NULL, NULL FROM control.etl_rechazo GROUP BY motivo;

-- Ejecución de los controles (salida informativa)
SELECT * FROM control.v_conciliacion_estado;
SELECT * FROM control.v_integridad;
SELECT * FROM control.v_excepciones;

/* =====================================================================================
   §8  CONSULTAS ANALÍTICAS PARAMETRIZADAS
   Versión SQL de las preguntas del enunciado y de las tres adicionales, escritas como sentencias
   preparadas (PREPARE / EXECUTE) para poder ejecutarlas y revisarlas en psql. El agente NO lee este
   archivo: genera consultas equivalentes desde su catálogo de 5 plantillas (CQ-01 a CQ-05 en
   agente/bdoo/consultas.py), con métricas y dimensiones de listas blancas y los VALORES siempre como
   parámetros. El SQL exacto que ejecutó el agente en cada caso está en la matriz de pruebas y en la BDOO.
   Reglas de cálculo:
     ingreso_neto    = SUM(cantidad*precio_unitario - descuento)        [sin impuestos]
     costo           = SUM(cantidad*costo_unitario)
     margen_bruto    = SUM(ingreso_neto - costo)
     margen_pct      = SUM(margen_bruto) / SUM(ingreso_neto)
     ticket_promedio = SUM(ingreso_neto) / COUNT(DISTINCT numero_ticket)
   ===================================================================================== */

-- Q1 ¿Cuál fue el ingreso neto por mes?  ($1 = desde, $2 = hasta)
PREPARE q1_ingreso_neto_por_mes(DATE, DATE) AS
SELECT f.anio_mes, SUM(v.ingreso_neto) AS ingreso_neto
FROM dm.fact_ventas v JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
WHERE f.fecha BETWEEN $1 AND $2
GROUP BY f.anio_mes ORDER BY f.anio_mes;
EXECUTE q1_ingreso_neto_por_mes('2025-01-01', '2026-09-30');

-- Q2 ¿Cuáles son las cinco categorías con mayor margen bruto?  ($3 = límite)
PREPARE q2_top_categorias_margen(DATE, DATE, INT) AS
SELECT p.categoria, SUM(v.margen_bruto) AS margen_bruto,
       ROUND(SUM(v.margen_bruto) / NULLIF(SUM(v.ingreso_neto), 0) * 100, 2) AS margen_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f    ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_producto p ON p.producto_sk = v.producto_sk
WHERE f.fecha BETWEEN $1 AND $2
GROUP BY p.categoria ORDER BY margen_bruto DESC LIMIT $3;
EXECUTE q2_top_categorias_margen('2025-01-01', '2026-09-30', 5);

-- Q3 ¿Qué sucursal presenta el ticket promedio más alto?
PREPARE q3_ticket_promedio_sucursal(DATE, DATE, INT) AS
SELECT s.nombre AS sucursal,
       ROUND(SUM(v.ingreso_neto) / NULLIF(COUNT(DISTINCT v.numero_ticket), 0), 2) AS ticket_promedio,
       COUNT(DISTINCT v.numero_ticket) AS tickets
FROM dm.fact_ventas v
JOIN dm.dim_fecha f    ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_sucursal s ON s.sucursal_sk = v.sucursal_sk
WHERE f.fecha BETWEEN $1 AND $2
GROUP BY s.nombre ORDER BY ticket_promedio DESC LIMIT $3;
EXECUTE q3_ticket_promedio_sucursal('2025-01-01', '2026-09-30', 1);

-- Q4 ¿Qué segmento de clientes redujo más su volumen de compra?
--    Periodo actual ($1..$2) vs periodo base ($3..$4). Segmento = el vigente al momento de la compra (SCD2).
PREPARE q4_variacion_segmento(DATE, DATE, DATE, DATE) AS
SELECT c.segmento,
       SUM(v.ingreso_neto) FILTER (WHERE f.fecha BETWEEN $3 AND $4) AS ingreso_base,
       SUM(v.ingreso_neto) FILTER (WHERE f.fecha BETWEEN $1 AND $2) AS ingreso_actual,
       SUM(v.ingreso_neto) FILTER (WHERE f.fecha BETWEEN $1 AND $2)
         - SUM(v.ingreso_neto) FILTER (WHERE f.fecha BETWEEN $3 AND $4) AS variacion,
       ROUND((SUM(v.ingreso_neto) FILTER (WHERE f.fecha BETWEEN $1 AND $2)
         / NULLIF(SUM(v.ingreso_neto) FILTER (WHERE f.fecha BETWEEN $3 AND $4), 0) - 1) * 100, 2) AS variacion_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f   ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_cliente c ON c.cliente_sk = v.cliente_sk
WHERE f.fecha BETWEEN $3 AND $4 OR f.fecha BETWEEN $1 AND $2
GROUP BY c.segmento ORDER BY variacion ASC;
EXECUTE q4_variacion_segmento('2026-01-01', '2026-09-30', '2025-01-01', '2025-09-30');

-- Q4-bis (justificación del SCD): mismo cálculo usando el segmento ACTUAL (equivale a SCD Tipo 1)
SELECT ca.segmento AS segmento_actual,
       SUM(v.ingreso_neto) FILTER (WHERE f.anio = 2025 AND f.mes <= 9) AS ingreso_base,
       SUM(v.ingreso_neto) FILTER (WHERE f.anio = 2026 AND f.mes <= 9) AS ingreso_actual
FROM dm.fact_ventas v
JOIN dm.dim_fecha f    ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_cliente c  ON c.cliente_sk = v.cliente_sk
JOIN dm.dim_cliente ca ON ca.cliente_id = c.cliente_id AND ca.es_actual
GROUP BY ca.segmento ORDER BY 1;

-- Q5 ¿Qué canal concentra el mayor valor de ventas?  (incluye participación %)
PREPARE q5_canal_mayor_venta(DATE, DATE, INT) AS
SELECT n.nombre AS canal, SUM(v.ingreso_neto) AS ingreso_neto,
       ROUND(100 * SUM(v.ingreso_neto) / SUM(SUM(v.ingreso_neto)) OVER (), 2) AS participacion_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_canal n ON n.canal_sk = v.canal_sk
WHERE f.fecha BETWEEN $1 AND $2
GROUP BY n.nombre ORDER BY ingreso_neto DESC LIMIT $3;
EXECUTE q5_canal_mayor_venta('2025-01-01', '2026-09-30', 5);

-- Q6 Compare el margen de dos canales durante los últimos tres meses disponibles
--    (los "últimos tres meses" se calculan sobre la fecha máxima del hecho, no sobre la fecha de hoy)
PREPARE q6_margen_dos_canales(TEXT, TEXT) AS
WITH limites AS (
    SELECT (DATE_TRUNC('month', MAX(f.fecha)) - INTERVAL '2 months')::DATE AS desde, MAX(f.fecha) AS hasta
    FROM dm.fact_ventas v JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
)
SELECT n.nombre AS canal, f.anio_mes, SUM(v.margen_bruto) AS margen_bruto,
       ROUND(SUM(v.margen_bruto) / NULLIF(SUM(v.ingreso_neto), 0) * 100, 2) AS margen_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_canal n ON n.canal_sk = v.canal_sk
CROSS JOIN limites l
WHERE f.fecha BETWEEN l.desde AND l.hasta AND n.nombre IN ($1, $2)
GROUP BY n.nombre, f.anio_mes ORDER BY n.nombre, f.anio_mes;
EXECUTE q6_margen_dos_canales('Tienda física', 'E-commerce web');

-- Q7 ¿Qué producto lidera las ventas dentro de una categoría y periodo determinados?
PREPARE q7_producto_lider(TEXT, DATE, DATE) AS
SELECT p.nombre AS producto, SUM(v.ingreso_neto) AS ingreso_neto, SUM(v.cantidad) AS unidades
FROM dm.fact_ventas v
JOIN dm.dim_fecha f    ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_producto p ON p.producto_sk = v.producto_sk
WHERE p.categoria = $1 AND f.fecha BETWEEN $2 AND $3
GROUP BY p.nombre ORDER BY ingreso_neto DESC LIMIT 1;
EXECUTE q7_producto_lider('Bebidas', '2026-04-01', '2026-06-30');

-- A1 (adicional) Concentración: ¿qué 10 clientes generan más ingreso y qué % del total representan?
--    Se agrupa por la CLAVE NATURAL del cliente (cliente_id): hay razones sociales repetidas entre clientes distintos.
PREPARE a1_concentracion_clientes(DATE, DATE, INT) AS
SELECT c.cliente_id, MIN(c.nombre) AS cliente, SUM(v.ingreso_neto) AS ingreso_neto,
       ROUND(100 * SUM(v.ingreso_neto) / SUM(SUM(v.ingreso_neto)) OVER (), 2) AS participacion_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f   ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_cliente c ON c.cliente_sk = v.cliente_sk
WHERE f.fecha BETWEEN $1 AND $2 AND v.cliente_sk > 0
GROUP BY c.cliente_id ORDER BY ingreso_neto DESC LIMIT $3;
EXECUTE a1_concentracion_clientes('2025-01-01', '2026-09-30', 10);

-- A2 (adicional) ¿Qué porcentaje de descuento otorga cada canal?
PREPARE a2_descuento_por_canal(DATE, DATE) AS
SELECT n.nombre AS canal, SUM(v.descuento) AS descuento,
       ROUND(SUM(v.descuento) / NULLIF(SUM(v.monto_bruto), 0) * 100, 2) AS descuento_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_canal n ON n.canal_sk = v.canal_sk
WHERE f.fecha BETWEEN $1 AND $2
GROUP BY n.nombre ORDER BY descuento_pct DESC;
EXECUTE a2_descuento_por_canal('2025-01-01', '2026-09-30');

-- A3 (adicional) ¿Qué productos tienen el margen porcentual más bajo?
PREPARE a3_productos_menor_margen(DATE, DATE, INT) AS
SELECT p.nombre AS producto, p.categoria, SUM(v.ingreso_neto) AS ingreso_neto, SUM(v.margen_bruto) AS margen_bruto,
       ROUND(SUM(v.margen_bruto) / NULLIF(SUM(v.ingreso_neto), 0) * 100, 2) AS margen_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f    ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_producto p ON p.producto_sk = v.producto_sk
WHERE f.fecha BETWEEN $1 AND $2
GROUP BY p.nombre, p.categoria ORDER BY margen_pct ASC LIMIT $3;
EXECUTE a3_productos_menor_margen('2025-01-01', '2026-09-30', 10);

DEALLOCATE ALL;
