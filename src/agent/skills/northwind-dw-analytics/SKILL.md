---
name: northwind-dw-analytics
description: "Consulta y analiza el Data Warehouse Northwind en PostgreSQL (hechos: Sales; dimensiones: Date, Product, Category, Customer, Supplier, Employee, Shipper, Territories, City, State, Country, Continent). Activar SIEMPRE ante consultas puntuales o análisis OLAP, KPIs (ventas, ticket promedio, descuentos, fletes, entregas, ABC) y gráficos sobre Northwind."
metadata:
  course-version: "1.0.0"
  course-activation: "northwind|cuánto|cuántos|cuál|qué|listar|mostrar|producto|categoría|precio|orden|pedido|cliente|empleado|proveedor|envío|flete|ciudad|país|continente|ventas|facturación|analizar|kpi|abc|pareto|ticket promedio|evolución|ranking|top|graficar|gráfico"
  course-negative-signals: "INSERT|UPDATE|DELETE|DROP|ALTER|crear tabla|borrar datos|saludo|hola|clima|receta"
  course-tool-hints: "execute_query_tool|summarize_dataframe_tool|create_plotly_chart_tool"
  course-resources: "references/dw-star-schema.md|references/kpi-definitions.md|references/chart-selection-guide.md|assets/executive-report-template.md"
  course-tags: "northwind|postgresql|data-warehouse|olap|snowflake|analytics|kpi|plotly"
---

# Flujo de trabajo Analítico

## Instrucciones

Seguí este marco de trabajo lógico para resolver las consultas del usuario:

- 1. Si el usuario manifiesta una preferencia, deseo, nueva regla de negocio, nueva definicion de KPI o alguna correccion, consultá con `recall_memory_tool` y  actualizala con `supersede_memory_tool` de otro modo si es algo nuevo guardalo con `save_memory_tool`.
- 2. Usá `load_skill_reference_tool` para leer el esquema de la base de datos e informacion adicional que necesites comprender del esquema, tablas y datos (`references/dw-star-schema.md`). Las métricas de negocio se encuentran en(`references/kpi-definitions.md`).
- 3. Diseñá tus consultas SQL y ejecútalas usando `execute_query_tool`. 
- 4. Solo si `execute_query_tool` te indica `metadata_only` (porque la tabla tiene demasiadas filas), usa `summarize_dataframe_tool` para inspeccionar el dataset en memoria.
- 5. Si el cliente solicita un gráfico, leé siempre antes la guía en `references/chart-selection-guide.md` y luego generá la visualización usando `create_plotly_chart_tool` con el `dataset_id` que obtuviste.
- 6. Cargá la plantilla ejecutiva `assets/executive-report-template.md` y estructura tus hallazgos.

## Reglas

- No respondas con consultas SQL salvo si el usuario te lo pide expresamente
- Antes de ejecutar una consulta SQL revisa el esquema de la base de datos.
- No uses comillas dobles o simples para nombrar tablas o columnas en las consultas SQL.
- Nunca incluyas código SQL ni expliques IDs de datasets en la respuesta final.
- Respetá siempre las reglas, preferencias y definiciones recuperadas de la memoria cuando apliquen al análisis o al formato de salida.

## Ejemplo

Si el usuario pide la evolución de ventas y los meses con más y menos ventas, además de un gráfico:
1. Consultá `recall_memory_tool` para verificar preferencias o reglas previas.
2. Leé el esquema de la base de datos con `load_skill_reference_tool`
3. Ejecutá una consulta SQL agrupando ventas por mes/año siguiendo (`references/dw-star-schema.md`). Si te devuelve los datos, ya podés leer toda la tendencia. (Si te devuele `metadata_only`, usa `summarize_dataframe_tool` para inspeccionar el dataset y obtener la tendencia de ventas.)
4. Consulta la guía de gráficos (`references/chart-selection-guide.md`) y usa `create_plotly_chart_tool` con el `dataset_id` de tu primera consulta (la de tendencia).
5. Redacta la respuesta ejecutiva final combinando todos los datos que recopilaste y apoyandote en `assets/executive-report-template.md`