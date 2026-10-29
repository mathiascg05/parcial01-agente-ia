# Evidencia de la BDOO (ZODB)

Archivo: `data/bdoo_evidencia/evidencia.fs` (FileStorage) · blobs (LOB): `data/bdoo_evidencia/evidencia_blobs/`

La base se cerró y se volvió a abrir antes de generar este documento: todo lo que sigue fue leído desde disco (persistencia real, no memoria del proceso).

## 1. Raíz de la base y objetos de configuración
- `root['agente']` → **AgenteAnalitico** IDO `0000000000000002`: Agente Analítico de Ventas v1.0 (5 consultas, 11 reglas)
- `root['usuarios']` → OOBTree con 2 usuarios; `root['sesiones']` → OOBTree con 1 sesión(es); `root['fuentes']` → 6 FuenteDato

| Objeto | Clase (herencia) | IDO |
|---|---|---|
| CQ-04 Comparación entre periodos | ConsultaComparativaPeriodos → ConsultaAnalitica → ObjetoAgente | `000000000000001f` |
| CQ-05 Comparación entre miembros | ConsultaComparativaMiembros → ConsultaAnalitica → ObjetoAgente | `0000000000000020` |
| CQ-03 Tendencia temporal | ConsultaTendencia → ConsultaAnalitica → ObjetoAgente | `0000000000000021` |
| CQ-02 Ranking por dimensión | ConsultaRanking → ConsultaAnalitica → ObjetoAgente | `0000000000000022` |
| CQ-01 Total del periodo | ConsultaTotal → ConsultaAnalitica → ObjetoAgente | `0000000000000023` |
| RV01 Operación autorizada (sólo lectura) | ReglaOperacionNoAutorizada → ReglaValidacion → ObjetoAgente | `0000000000000014` |
| RV02 Alcance del Data Mart | ReglaAlcanceDataMart → ReglaValidacion → ObjetoAgente | `0000000000000015` |
| RV03 Dimensión existente | ReglaDimensionExistente → ReglaValidacion → ObjetoAgente | `0000000000000016` |
| RV04 Criterio explícito (ambigüedad) | ReglaCriterioExplicito → ReglaValidacion → ObjetoAgente | `0000000000000017` |
| RV05 Valores de filtro existentes | ReglaValoresFiltro → ReglaValidacion → ObjetoAgente | `0000000000000018` |
| RV06 Periodo disponible | ReglaPeriodoDisponible → ReglaValidacion → ObjetoAgente | `0000000000000019` |
| RV07 SQL seguro de sólo lectura | ReglaSQLSoloLectura → ReglaValidacion → ObjetoAgente | `000000000000001a` |
| RV08 Resultado con registros | ReglaResultadoNoVacio → ReglaValidacion → ObjetoAgente | `000000000000001b` |
| RV09 Miembros desconocidos | ReglaMiembrosDesconocidos → ReglaValidacion → ObjetoAgente | `000000000000001c` |
| RV10 Consistencia de totales | ReglaConsistenciaTotales → ReglaValidacion → ObjetoAgente | `000000000000001d` |
| RV11 Narrativa respaldada por datos | ReglaNarrativaRespaldada → ReglaValidacion → ObjetoAgente | `000000000000001e` |
| Usuario Gerencia General | Gerente → Usuario → ObjetoAgente | `0000000000000006` |
| Usuario Analista de Datos | Analista → Usuario → ObjetoAgente | `0000000000000007` |

## 2. Sesión completa: pregunta → intención → consulta → resultado → respuesta
**Sesion** `S-20261029-110003-741` · IDO `000000000000002e` · usuario → IDO `0000000000000006` (gerente Gerencia General (V-12345678)) · resumen {'preguntas': 5, 'por_estado': {'RESPONDIDA': 2, 'ACLARACION': 1, 'SIN_DATOS': 1, 'RECHAZADA': 1}}

### 2.1 «¿Qué canal concentra el mayor valor de ventas en 2026?»  → estado **RESPONDIDA**
- **Pregunta** IDO `0000000000000031` · historial de estados: RECIBIDA → INTERPRETADA → RESPONDIDA
- **Intencion** IDO `0000000000000033` · origen reglas · intención=analizar_canales | operación=ranking | métrica=ingreso_neto | dimensión=canal | periodo=año 2026 | orden=desc | límite=1
- **ConsultaAnalitica** (apuntador) IDO `0000000000000022` · CQ-02 v2 — Ranking por dimensión
- **ResultadoConsulta** IDO `0000000000000036` · 1 fila(s) en 15.44 ms · LOB CSV de 69 bytes
```sql
SELECT n.nombre AS canal, SUM(v.ingreso_neto) AS ingreso_neto, ROUND(100.0 * SUM(v.ingreso_neto) / NULLIF(SUM(SUM(v.ingreso_neto)) OVER (), 0), 2) AS participacion_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_canal n ON n.canal_sk = v.canal_sk
WHERE f.fecha BETWEEN %(p_desde)s AND %(p_hasta)s
GROUP BY n.nombre
ORDER BY (n.nombre::TEXT ILIKE '%%sin correspondencia%%' OR n.nombre::TEXT ILIKE '%%no informad%%' OR n.nombre::TEXT ILIKE '%%consumidor final%%'), ingreso_neto DESC NULLS LAST, canal
LIMIT %(limite)s
```
Parámetros: `{'p_desde': '2026-01-01', 'p_hasta': '2026-12-31', 'limite': 1}`
- **RespuestaAgente** IDO `0000000000000034` · tipo **RESPUESTA**
  > Canal con mayor ingreso neto en año 2026: Mayorista B2B (USD 580.518,89, 42,06 % del total).
- **FuenteDato** (apuntadores): `dm.dim_canal` IDO `0000000000000013`, `dm.dim_fecha` IDO `000000000000000f`, `dm.fact_ventas` IDO `000000000000000e`
- Advertencias: El periodo año 2026 sólo está cubierto parcialmente (datos disponibles 01-01-2025 a 30-09-2026).
- Reglas aplicadas: RV01✔, RV02✔, RV03✔, RV04✔, RV05✔, RV06✘, RV07✔, RV08✔, RV09✔

### 2.2 «¿y en 2025?»  → estado **RESPONDIDA**
- **Pregunta** IDO `0000000000000046` · historial de estados: RECIBIDA → INTERPRETADA → RESPONDIDA
- **Intencion** IDO `0000000000000048` · origen reglas · intención=analizar_canales | operación=ranking | métrica=ingreso_neto | dimensión=canal | periodo=año 2025 | orden=desc | límite=1
- **ConsultaAnalitica** (apuntador) IDO `0000000000000022` · CQ-02 v2 — Ranking por dimensión
- **ResultadoConsulta** IDO `000000000000004b` · 1 fila(s) en 17.42 ms · LOB CSV de 68 bytes
```sql
SELECT n.nombre AS canal, SUM(v.ingreso_neto) AS ingreso_neto, ROUND(100.0 * SUM(v.ingreso_neto) / NULLIF(SUM(SUM(v.ingreso_neto)) OVER (), 0), 2) AS participacion_pct
FROM dm.fact_ventas v
JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_canal n ON n.canal_sk = v.canal_sk
WHERE f.fecha BETWEEN %(p_desde)s AND %(p_hasta)s
GROUP BY n.nombre
ORDER BY (n.nombre::TEXT ILIKE '%%sin correspondencia%%' OR n.nombre::TEXT ILIKE '%%no informad%%' OR n.nombre::TEXT ILIKE '%%consumidor final%%'), ingreso_neto DESC NULLS LAST, canal
LIMIT %(limite)s
```
Parámetros: `{'p_desde': '2025-01-01', 'p_hasta': '2025-12-31', 'limite': 1}`
- **RespuestaAgente** IDO `0000000000000049` · tipo **RESPUESTA**
  > Canal con mayor ingreso neto en año 2025: Mayorista B2B (USD 991.784,36, 46,90 % del total).
- **FuenteDato** (apuntadores): `dm.dim_canal` IDO `0000000000000013`, `dm.dim_fecha` IDO `000000000000000f`, `dm.fact_ventas` IDO `000000000000000e`
- Advertencias: Pregunta de seguimiento: se reutilizó el contexto de la pregunta anterior de la sesión.
- Reglas aplicadas: RV01✔, RV02✔, RV03✔, RV04✔, RV05✔, RV06✔, RV07✔, RV08✔, RV09✔

### 2.3 «¿Cuál fue el mejor canal?»  → estado **ACLARACION**
- **Pregunta** IDO `000000000000005b` · historial de estados: RECIBIDA → INTERPRETADA → ACLARACION
- **Intencion** IDO `000000000000005d` · origen reglas · [ambigua] La pregunta no indica el criterio de evaluación. Puede medirse por ingreso neto, margen bruto, cantidad vendida (unidades) o ticket promedio.
- **RespuestaAgente** IDO `000000000000005e` · tipo **ACLARACION**
  > La pregunta no indica el criterio de evaluación. Puede medirse por ingreso neto, margen bruto, cantidad vendida (unidades) o ticket promedio. ¿Con qué criterio desea evaluarlo?
- Reglas aplicadas: RV01✔, RV02✔, RV03✔, RV04✘

### 2.4 «¿Cuánto vendimos de Jardinería en 2025?»  → estado **SIN_DATOS**
- **Pregunta** IDO `0000000000000068` · historial de estados: RECIBIDA → INTERPRETADA → SIN_DATOS
- **Intencion** IDO `000000000000006a` · origen reglas · intención=analizar_ventas | operación=total | métrica=ingreso_neto | dimensión=— | periodo=año 2025 | filtros=Categoría = Jardinería | orden=desc
- **ConsultaAnalitica** (apuntador) IDO `0000000000000023` · CQ-01 v1 — Total del periodo
- **ResultadoConsulta** IDO `000000000000006d` · 0 fila(s) en 6.93 ms · LOB CSV de 0 bytes
```sql
SELECT SUM(v.ingreso_neto) AS ingreso_neto, COUNT(*) AS lineas
FROM dm.fact_ventas v
JOIN dm.dim_fecha f ON f.fecha_sk = v.fecha_sk
JOIN dm.dim_producto p ON p.producto_sk = v.producto_sk
WHERE f.fecha BETWEEN %(p_desde)s AND %(p_hasta)s
  AND p.categoria = ANY(%(f0)s)
HAVING COUNT(*) > 0
```
Parámetros: `{'p_desde': '2025-01-01', 'p_hasta': '2025-12-31', 'f0': ['Jardinería']}`
- **RespuestaAgente** IDO `000000000000006b` · tipo **SIN_DATOS**
  > No hay registros en el Data Mart para ingreso neto con Categoría = Jardinería en año 2025. El resultado está vacío: no se reporta como cero porque no hubo ventas registradas que lo respalden.
- **FuenteDato** (apuntadores): `dm.dim_fecha` IDO `000000000000000f`, `dm.dim_producto` IDO `0000000000000010`, `dm.fact_ventas` IDO `000000000000000e`
- Reglas aplicadas: RV01✔, RV02✔, RV03✔, RV04✔, RV05✔, RV06✔, RV07✔, RV08✘

### 2.5 «Borra las ventas de enero de 2026»  → estado **RECHAZADA**
- **Pregunta** IDO `000000000000007b` · historial de estados: RECIBIDA → INTERPRETADA → RECHAZADA
- **Intencion** IDO `000000000000007d` · origen regla RV01 · [operacion_no_autorizada] Operación no autorizada (modificar o eliminar datos). El agente sólo realiza consultas de lectura sobre el Data Mart de ventas.
- **RespuestaAgente** IDO `000000000000007e` · tipo **RECHAZO**
  > Operación no autorizada (modificar o eliminar datos). El agente sólo realiza consultas de lectura sobre el Data Mart de ventas.
- Reglas aplicadas: RV01✘

## 3. Identidad de objeto y objetos compartidos
Las respuestas 2.1 y 2.2 apuntan al **mismo objeto** FuenteDato `dm.fact_ventas` (misma identidad, no una copia):
- `r1.fuentes['dm.fact_ventas'] is r2.fuentes['dm.fact_ventas']` → **True** · IDO `000000000000000e` · usos registrados: 3
- Ambos resultados apuntan a la misma ConsultaAnalitica: **True** (IDO `0000000000000022`)
- Memoria operativa: `sesion.contexto()['ultima_intencion']` es la Intencion IDO `0000000000000048` (la de la pregunta 2.2, que reutilizó la 2.1).

## 4. LOB (Blob) asociado a un ResultadoConsulta
```csv
canal,ingreso_neto,participacion_pct
Mayorista B2B,580518.89,42.06
```

## 5. Encapsulamiento, TDA y polimorfismo
- TDA `DocumentoIdentidad.formato('V-12345678')` → `V-12345678` (tipo Venezolano); un valor inválido lanza ErrorTDA (ver tests).
- Polimorfismo de Usuario: `Gerente.nivel_detalle()` = `ejecutivo`, muestra SQL = False; `Analista.nivel_detalle()` = `tecnico`, muestra SQL = True.
- Polimorfismo de ConsultaAnalitica: el agente envía el mismo mensaje `aplica_a(intencion)` a cada consulta del catálogo y `construir_sql(intencion)` a la elegida; cada subclase responde distinto.
- Polimorfismo de ReglaValidacion: `aplicar(ctx)` (método plantilla) → `validar(ctx)` específico de cada regla. Estadísticas persistidas: RV01: 5 eval./1 fallos, RV02: 4 eval./0 fallos, RV03: 4 eval./0 fallos, RV04: 4 eval./1 fallos, RV05: 3 eval./0 fallos, RV06: 3 eval./1 fallos, RV07: 3 eval./0 fallos, RV08: 3 eval./1 fallos, RV09: 2 eval./0 fallos, RV10: 0 eval./0 fallos, RV11: 0 eval./0 fallos

## 6. Versionamiento
- Versionamiento explícito de `CQ-02` (IDO `0000000000000022`): versión actual **v2**
  - v1 · 2026-10-29T11:00:03 · Versión inicial
  - v2 · 2026-10-29T11:00:03 · Se agrega desempate por nombre de miembro en el ORDER BY
- Historial interno de ZODB para el mismo OID: cada transacción que modificó el objeto (cada ejecución incrementa su contador y la última agregó la v2) dejó una revisión recuperable:

| tid | fecha | tamaño |
|---|---|---|
| `040ca96410c89fbb` | 2026-10-29 11:00:03.933677 | 539 bytes |
| `040ca964107a35cc` | 2026-10-29 11:00:03.861887 | 539 bytes |
| `040ca96410448699` | 2026-10-29 11:00:03.812737 | 539 bytes |
| `040ca9640ff51888` | 2026-10-29 11:00:03.740017 | 539 bytes |

## 7. Transacciones y recuperación
Cada pregunta se procesó dentro de una transacción ZODB (`RepositorioBDOO.transaccion()`): si algo falla se hace `abort()` y no queda ningún objeto a medio guardar; ante un `ConflictError` (dos procesos modificando el mismo objeto) se reintenta. FileStorage es un log de sólo-anexión, lo que permite recuperar versiones anteriores.