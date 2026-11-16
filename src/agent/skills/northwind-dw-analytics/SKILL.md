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

Ejecuta estrictamente los siguientes pasos en forma secuencial como se explica abajo sin excepción:

1. Analiza la consulta del cliente e identifica hechos, dimensiones a mapear y metricas o KPIs necesarios a calcular
2. Leé `references/dw-star-schema.md` para extraer las tablas y datos necesarios para responder. Si faltan datos para el pedido, informar el límite exacto sin asumir valores.
3. Diseñá el cubo de datos y construí mentalmente tu consulta SQL:
- Partí del grano mínimo Sales(OrderDateKey, ProductKey, CustomerKey) y agregá (roll-up) respetando las cadenas Snowflake de `references/dw-star-schema.md` y las dimensiones identificadas en el paso 1. Para consultar tablas, columnas y tipos de datos usa `load_skill_reference_tool`
- Leé references/kpi-definitions.md y calculá las metricas o KPIs identificados en el paso 1. Para consultar definiciones usa `load_skill_reference_tool`
4. Ejecutá la consulta SQL diseñada en el paso 3 contra la DB Northwind. Usa `execute_query_tool`
5. Si el resultado indica `metadata_only` (más de 10 filas), debes invocar inmediatamente `summarize_dataframe_tool` pasando el `dataset_id` obtenido para analizar los valores.
6. Analizá e interpretá los resultados obtenidos hasta el momento.
7. Graficá (Si el cliente lo solicita) leyendo previamente `references/chart-selection-guide.md` para elegir el literal exacto de chart_type y mapear dimensiones y metricas/KPIs en `create_plotly_chart_tool`. Obligatorio: describí cada gráfico generado explicando qué muestra y los hallazgos principales observados.
8. Respuesta final obligatoria. responde:
- Con un dato puntual (sin gráfico): Si el usuario pregunta por una respuesta directa, elaborá una respuesta contreta con los resultados obtenidos sin adicionales.
- Con un análisis/agregación o con un gráfico: verificá que todos los resultados sean coherentes y cierren. Formulá un breve analisis usando como plantilla `assets/executive-report-template.md`.

## Rules

- No uses comillas dobles o simples para llamar las tablas o columnas en las consultas SQL.
- En tu respuesta final (paso 5) nunca incluyas ni expliques tus consultas SQL, procedimeintos ni tecnicas aplicadas salvo expreso pedido del cliente

## Example

Si el usuario pide "¿Cómo fue la evolución mensual de mis ventas?" Debes seguir el workflow: consultar las referencias de esquema, diseñar la consulta SQL que responde la pregunta, invocar `execute_query_tool` para obtener los datos y responder únicamente analizando y dando una breve explicacion al cliente no efrencindo explicaciones innecesarias de procesos y tecnicas seguidas