---
name: northwind-dw-analytics
description: Consulta y analiza el Data Warehouse Northwind en PostgreSQL (hechos: Sales; dimensiones: Date, Product, Category, Customer, Supplier, Employee, Shipper, Territories, City, State, Country, Continent). Activar SIEMPRE ante consultas puntuales o análisis OLAP, KPIs (ventas, ticket promedio, descuentos, fletes, entregas, ABC) y gráficos sobre Northwind.
metadata:
  course-version: "1.0.0"
  course-activation: "northwind|cuánto|cuántos|cuál|qué|listar|mostrar|producto|categoría|precio|orden|pedido|cliente|empleado|proveedor|envío|flete|ciudad|país|continente|ventas|facturación|analizar|kpi|abc|pareto|ticket promedio|evolución|ranking|top"
  course-negative-signals: "INSERT|UPDATE|DELETE|DROP|ALTER|crear tabla|borrar datos|saludo|hola|clima|receta"
  course-tool-hints: "execute_query_tool|summarize_dataframe_tool|create_plotly_chart_tool"
  course-resources: "references/dw-star-schema.md|references/kpi-definitions.md|assets/executive-report-template.md"
  course-tags: "northwind|postgresql|data-warehouse|olap|snowflake|analytics|kpi"
---

# Northwind DW Analytics

## Workflow

1. **Validar esquema:** Leer `references/dw-star-schema.md`. Prohibido inventar tablas/columnas (no existe inventario/stock ni costos). Si faltan datos para el pedido, informar el límite exacto sin asumir valores.
2. **Fijar ventana temporal:** Ejecutar `execute_query_tool` con `SELECT MIN(d."Date"), MAX(d."Date") FROM "Sales" s JOIN "Date" d ON s."OrderDateKey" = d."DateKey"` (respetar mayúsculas entre comillas en PostgreSQL). Nunca inferir fechas relativas ("hoy", "año actual") sin contrastar con este rango.
3. **Diseñar cubo y SQL (PostgreSQL):**
   - Partir del grano mínimo `Sales(OrderDateKey, ProductKey, CustomerKey)` y hacer roll-up siguiendo las jerarquías de `references/dw-star-schema.md`.
   - Leer `references/kpi-definitions.md` y resolver cálculos complejos (`COUNT(DISTINCT ...)`, deduplicación de `Freight`, ventanas `SUM() OVER` para ABC/Pareto) **dentro del SQL** en `execute_query_tool`, ya que `summarize_dataframe_tool` solo admite agregaciones básicas (`sum`, `mean`, `count`, `min`, `max`, `describe`).
4. **Inspeccionar o resumir `dataset_id`:**
   - Si `execute_query_tool` devuelve >10 filas (solo metadata), usar `summarize_dataframe_tool` sobre el `dataset_id` (generando `summary_dataset_id`) o acotar la consulta SQL (`LIMIT` / `GROUP BY`) para leer los valores exactos.
5. **Graficar:** Si hay series temporales, rankings o Pareto/ABC, invocar `create_plotly_chart_tool` (`líneas`, `barras`, `pie`, `áreas`) pasando el `dataset_id` o `summary_dataset_id` ya agregado.
6. **Responder:**
   - **Dato puntual:** Respuesta directa con el valor exacto y fecha de corte.
   - **Análisis/Agregación:** Verificar cierre de totales y redactar según `assets/executive-report-template.md`.

## Reglas de Ejecución

- Encadenar herramientas mediante `dataset_id` / `summary_dataset_id` sin pedir al usuario que reingrese datos intermedios.
- Prohibido imputar nulos o alterar registros históricos; reportar anomalías en limitaciones.