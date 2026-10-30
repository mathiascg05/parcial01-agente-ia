# Matriz de pruebas en vivo con OpenRouter (30-10-2026)

Ejecución del equipo en su computadora (macOS, Python 3.12, PostgreSQL 16) con la API key `parcial1`:

    python scripts/ejecutar_pruebas.py --modo auto --equipo 02

A diferencia de las corridas grabadas en esta carpeta (lotes enviados por el chat web), aquí el agente llama al
LLM (`openai/gpt-4o-mini`) **una vez por pregunta**, con el contexto de la sesión, como en uso real.

**Resultado: 32/35.** Las tres fallas:

| Caso | Pregunta | Qué hizo el LLM | Resultado |
|---|---|---|---|
| P04 | ¿Qué segmento de clientes redujo más su volumen de compra? | `faltan_parametros`: «Se requiere un periodo específico para comparar el volumen de compra.» | ACLARACION (RV04) en vez de respuesta |
| P23b | ¿y en 2026? (seguimiento de P23a) | Interpretó bien: margen bruto de 2026 (USD 309.100,73, cifra correcta) | Faltó la marca de «pregunta de seguimiento», que el agente muestra al usuario y registra en la BDOO |
| P29 | Compara el ingreso neto de Chacao y Lechería en 2025 | `faltan_parametros`: «Falta especificar el periodo para la comparación.» (el periodo sí estaba: 2025) | ACLARACION (RV04) en vez de respuesta |

**Corrección** (`anclar()` en `agente/interpretes/llm.py`):

- Si el LLM pide parámetros, pero la lectura literal entiende la pregunta completa, se usa la lectura literal y el ajuste queda como supuesto visible.
- En los seguimientos se conserva la marca de la lectura literal.

Se agregaron dos pruebas unitarias con estos casos, y una simulación de la matriz completa con estas tres respuestas da 35/35.
La verificación final es repetir el comando anterior después de `git pull`.
