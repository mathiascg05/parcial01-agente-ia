# Parcial 01 · Agente analítico de IA con Data Mart y BDOO

**Tópicos Especiales para la Gestión de Datos, UCAB.** Prof. Armen Djenanian.
Empresa del caso (ficticia): **Distribuidora Ávila C.A.**, con ventas de ene-2025 a sep-2026, 7 sucursales, 5 canales y 4 segmentos.

El agente recibe preguntas gerenciales en lenguaje natural y las resuelve en este orden:

1. Identifica la intención: métrica, dimensión, periodo, filtros, operación y límite.
2. Elige una **consulta parametrizada** de un catálogo.
3. Consulta el **Data Mart** en PostgreSQL con un rol de solo lectura.
4. Valida el resultado con 11 reglas.
5. Responde con evidencia: la cifra, la regla de cálculo, el periodo, los filtros, la fuente y el SQL.
6. Registra toda la interacción como objetos en una **BDOO (ZODB)**.

> **Principio rector:** el Data Mart contiene la verdad analítica, la BDOO guarda los objetos y la trazabilidad del agente, y el agente conecta la pregunta con una respuesta sustentada.

```
Pregunta ─► RV01 (texto) ─► Intérprete (LLM OpenRouter │ reglas) ─► Intencion ─► RV02–RV06
        ─► ConsultaAnalitica.aplica_a() / construir_sql() ─► RV07 (SQL seguro)
        ─► PostgreSQL dm.* (rol agente_lector, READ ONLY) ─► ResultadoConsulta ─► RV08–RV10
        ─► RespuestaAgente (+ RV11 si narra el LLM) ─► commit en ZODB (Sesion → Pregunta → …)
```

## Estructura

| Ruta | Contenido |
|---|---|
| `data/generar_dataset.py` | Genera la fuente operacional (CSV) de forma determinista. Trae errores de calidad sembrados a propósito. |
| `data/fuente/*.csv` | Fuente operacional: tickets, detalle, clientes e historial de segmento, productos, sucursales y canales. |
| `sql/Datamart.sql` | **Script completo:** esquemas `oltp`/`dm`/`control`, estrella, SCD2, ETL, rol de solo lectura, controles de integridad y conciliación, y consultas `PREPARE`. |
| `agente/catalogo.py` | Capa semántica: listas blancas de métricas, dimensiones, joins y fuentes. |
| `agente/bdoo/` | **BDOO:** `modelo.py` (clases), `consultas.py`, `reglas.py`, `agente_analitico.py`, `tda.py`, `repositorio.py` (ZODB). |
| `agente/interpretes/` | Intérprete por LLM (OpenRouter), por reglas y el híbrido (patrón Strategy). |
| `agente/redactor.py` | Respuesta gerencial y formato de las cifras. |
| `app/streamlit_app.py` | Interfaz web: chat, evidencia, explorador de la BDOO y catálogo. |
| `agente/cli.py` | Interfaz de consola. |
| `scripts/` | `setup_datamart.py`, `inicializar_bdoo.py`, `ejecutar_pruebas.py`, `evidencia_bdoo.py`. |
| `tests/` | Pruebas unitarias con pytest. |
| `docs/` | Diagramas, evidencias (conciliación, BDOO, pruebas) y guía de defensa. |

## Instalación y ejecución (unos 10 minutos)

Requisitos: Python 3.10 o superior, y PostgreSQL 14 o superior (o Docker con `docker compose up -d`).

```bash
# 1. Entorno
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # completar PG_ADMIN_PASSWORD, PG_PASSWORD y (opcional) OPENROUTER_API_KEY

# 2. Data Mart: crea la base, carga, aplica el ETL, crea el rol de solo lectura y concilia
python scripts/setup_datamart.py --crear-db
#    (alternativa con psql, desde la raíz:  createdb parcial01 && psql -d parcial01 -f sql/Datamart.sql)

# 3. BDOO
python scripts/inicializar_bdoo.py

# 4. Usar el agente
streamlit run app/streamlit_app.py                     # interfaz web
python -m agente.cli -p "¿Qué canal concentra el mayor valor de ventas?"   # consola

# 5. Pruebas
pytest -q                                              # unitarias
python scripts/ejecutar_pruebas.py --equipo XX         # matriz -> entregables/EquipoXX_Pruebas.xlsx
python scripts/evidencia_bdoo.py                       # evidencia -> docs/evidencias/evidencia_bdoo.md
```

**LLM:** sin `OPENROUTER_API_KEY` el agente funciona igual con el intérprete por reglas, que es determinista y no necesita internet. Con la clave, el modo `auto` usa el LLM para interpretar y para redactar la interpretación gerencial. Si el LLM falla o menciona cifras que no están en el resultado, el agente vuelve a las reglas o a la plantilla (regla RV11). El modelo se cambia con `OPENROUTER_MODEL`.

**Nota sobre ZODB:** FileStorage admite **un solo proceso**. Si Streamlit está abierto, el CLI no puede abrir la misma base. Ciérrelo o use otro archivo (`ZODB_PATH=...`). Los scripts de pruebas y de evidencia usan su propio archivo cuando la base principal está ocupada.

## Resultados de verificación

- Conciliación del Data Mart contra la fuente: **7/7 OK** en SQL y **5/5 OK** con pandas, de forma independiente.
- Integridad: **10/10 controles OK**.
- Matriz de pruebas: **35/35 OK**. El valor esperado se calcula con pandas directamente sobre los CSV; P25–P34 son regresiones de una revisión independiente.
- Pruebas unitarias: **35/35 OK**.
