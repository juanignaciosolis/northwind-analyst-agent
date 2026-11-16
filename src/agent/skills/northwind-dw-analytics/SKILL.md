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

# Northwind DW Analytics

## Workflow Analítico

Seguí este marco de trabajo lógico para resolver las consultas del usuario:

- **1. Contexto y Diseño:** Usá `load_skill_reference_tool` para leer el esquema (`references/dw-star-schema.md`) y las métricas (`references/kpi-definitions.md`).
- **2. Extracción de Datos:** Diseñá tus consultas SQL y ejecútalas usando `execute_query_tool`. 
- **3. Análisis de Dataset Extensos:** Solo si `execute_query_tool` te indica `metadata_only` (porque la tabla tiene demasiadas filas), usa `summarize_dataframe_tool` para inspeccionar el dataset en memoria.
- **4. Visualización:** Si el cliente solicita un gráfico, leé la guía en `references/chart-selection-guide.md` y luego generá la visualización usando `create_plotly_chart_tool` con el `dataset_id` que obtuviste.
- **5. Respuesta Final:** Cargá la plantilla ejecutiva `assets/executive-report-template.md` y estructura tus hallazgos.

## Rules
- No uses comillas dobles o simples para nombrar tablas o columnas en las consultas SQL.
- Nunca incluyas código SQL ni expliques IDs de datasets en la respuesta final.

## Example: "Evolución mensual y extremos"

Si el usuario pide la evolución de ventas y los meses con más y menos ventas, además de un gráfico:
1. Lee el esquema de la base de datos.
2. Ejecuta una consulta SQL agrupando ventas por mes/año. Si te devuelve los datos, ya podés leer toda la tendencia. (Si te devuele `metadata_only`, usa `summarize_dataframe_tool` para inspeccionar el dataset y obtener la tendencia de ventas.)
4. Consulta la guía de gráficos y usa `create_plotly_chart_tool` con el `dataset_id` de tu primera consulta (la de tendencia).
5. Redacta la respuesta ejecutiva final combinando todos los datos que recopilaste.