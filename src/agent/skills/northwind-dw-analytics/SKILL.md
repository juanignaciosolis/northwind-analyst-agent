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

## Workflow

1. Validar esquema: leer references/dw-star-schema.md. Si faltan datos para el pedido, informar el límite exacto sin asumir valores.
2. Fijar ventana temporal: ejecutar execute_query_tool con SELECT MIN(d."Date"), MAX(d."Date") FROM "Sales" s JOIN "Date" d ON s."OrderDateKey" = d."DateKey". Nunca inferir fechas relativas sin contrastar con este rango.
3. Diseñar cubo y SQL:
- Partir del grano mínimo Sales(OrderDateKey, ProductKey, CustomerKey) y agregar (roll-up) respetando las cadenas Snowflake de references/dw-star-schema.md.
- Leer references/kpi-definitions.md y resolver KPIs en execute_query_tool.
4. Graficar (si aplica): leer references/chart-selection-guide.md para elegir el literal exacto de chart_type y mapear dimensions y metrics en create_plotly_chart_tool. Obligatorio: describir cada gráfico generado explicando qué muestra y los hallazgos principales observados.
5. Responder:
- Dato puntual (sin gráfico): respuesta directa con valor exacto y fecha de corte.
- Análisis/Agregación o con gráfico: verificar cierre de totales y usar assets/executive-report-template.md.

## Reglas

- Encadenar tools mediante dataset_id y summary_dataset_id.
- Prohibido imputar nulos o alterar registros históricos; documentar anomalías en limitaciones.
