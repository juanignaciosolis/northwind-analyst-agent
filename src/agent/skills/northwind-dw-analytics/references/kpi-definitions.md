# Fórmulas KPI en Northwind DW

Resolver en execute_query_tool para dejar el dataset_id listo para summarize_dataframe_tool o create_plotly_chart_tool:

- Facturación Neta: SUM(s."SalesAmount")
- Unidades Vendidas: SUM(s."Quantity")
- Descuento Ponderado: SUM(s."UnitPrice" * s."Quantity" * s."Discount") / NULLIF(SUM(s."UnitPrice" * s."Quantity"), 0)
- Ticket Promedio: SUM(s."SalesAmount") / NULLIF(COUNT(DISTINCT s."CustomerKey"), 0)
- Flete (Freight): verificar si repite por OrderNo o prorratea por línea. Si repite, deduplicar en CTE (SELECT "OrderNo", MAX("Freight") AS freight FROM "Sales" GROUP BY "OrderNo") antes de sumar.
- ABC (Pareto): SUM(ventas) OVER (ORDER BY ventas DESC ROWS UNBOUNDED PRECEDING) * 100.0 / SUM(ventas) OVER () AS pct_acum -> A (<=80), B (>80 y <=95), C (>95).
- Lead Time Despacho (días): AVG(d_ship."Date" - d_ord."Date")
- Entregas a Tiempo (%): COUNT(DISTINCT CASE WHEN d_ship."Date" <= d_due."Date" THEN s."OrderNo" END) * 100.0 / NULLIF(COUNT(DISTINCT s."OrderNo"), 0)