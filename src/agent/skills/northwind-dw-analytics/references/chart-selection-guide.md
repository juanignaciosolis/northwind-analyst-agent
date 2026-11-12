# Guía de Gráficos (create_plotly_chart_tool)

Usar exclusivamente estos literales en chart_type:

- Participación sobre total (<= 5 categorías, 1 métrica): "pie chart" | dimensions=[cat], metrics=[val]
- Evolución temporal (1 serie continua): "lineas" | dimensions=[tiempo], metrics=[val]
- Evolución temporal (<= 5 categorías o varias métricas sin apilar): "multilineas" | dimensions=[tiempo, cat], metrics=[val] o metrics=[m1, m2]
- Evolución temporal acumulada bajo curva (1 serie): "area char" | dimensions=[tiempo], metrics=[val]
- Evolución temporal acumulada (múltiples series): "multiareachart" | dimensions=[tiempo, cat], metrics=[val] o metrics=[m1, m2]
- Evolución temporal de varias categorías mostrando composición del total: "column stacker bar" | dimensions=[tiempo, cat], metrics=[val] o metrics=[m1, m2]
- Categorías ordinales sin temporalidad ( rangos, ABC): "column bar" | dimensions=[cat], metrics=[val]
- Muchas categorías nominales (> 5, rankings/top) o etiquetas largas: "horizontal bar" | dimensions=[cat], metrics=[val] (ordenar SQL ASC para mayor arriba)
- Muchas categorías nominales desglosadas por segmento: "horizontal stacker bar" | dimensions=[cat, subcat], metrics=[val]