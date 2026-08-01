import json
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from rich.console import Console



# Rutas de los artefactos
ARTIFACTS_DIR = Path("artifacts")
JSONL_HISTORIA = ARTIFACTS_DIR / "eval_history.jsonl"
GRAFICO_PNG = ARTIFACTS_DIR / "precision_evolucion.png"
REPORTE_MD = ARTIFACTS_DIR / "REPORTE_EVALUACIONES.md"


def registrar_evaluacion(resumen: dict) -> None:
    """
    Registra una corrida de evaluación, genera el gráfico de tendencia
    y actualiza el reporte histórico en Markdown.
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    console = Console()

    # 1. Persistencia: Append de la corrida actual en formato JSONL
    with open(JSONL_HISTORIA, "a", encoding="utf-8") as f:
        f.write(json.dumps(resumen, ensure_ascii=False) + "\n")

    # 2. Cargar todo el historial acumulado con Pandas
    df = pd.read_json(JSONL_HISTORIA, lines=True)

    # Aseguramos que la fecha sea de tipo datetime para el eje X
    df["fecha"] = pd.to_datetime(df["fecha"])

    plt.figure(figsize=(9, 4.5))
    
    # Graficamos la línea
    plt.plot(
        df["fecha"], 
        df["precision"] * 100, 
        marker="o", 
        linewidth=2, 
        color="#2b5c8f", 
        label="% Precisión"
    )
    
    plt.title(
        "📈 Evolución Temporal del Porcentaje de Aciertos",
        fontsize=12,
        fontweight="bold",
    )
    plt.xlabel("Fecha y Hora")
    
    # Ajustamos el límite superior para que las etiquetas no se corten
    plt.ylim(0, 115) 
    
    # Dejamos solo la grilla vertical, es más limpio
    plt.grid(True, linestyle="--", alpha=0.4, axis="x")
    plt.xticks(rotation=25)

    # --- NUEVA LÓGICA: Etiquetas sobre cada punto ---
    for x, y in zip(df["fecha"], df["precision"] * 100):
        plt.annotate(
            f"{y:.1f}%",             # Formato: 1 decimal + %
            (x, y),                  # Posición (x, y)
            textcoords="offset points", 
            xytext=(0, 10),          # 10 puntos arriba del punto
            ha="center",             # Centrado horizontalmente
            fontsize=9,
            fontweight="bold",
            color="#333333"
        )

    # --- NUEVA LÓGICA: Ocultar el eje Y ---
    ax = plt.gca()
    ax.get_yaxis().set_visible(False) # Oculta marcas y números del eje Y
    ax.spines["left"].set_visible(False) # Oculta la línea vertical izquierda
    ax.spines["top"].set_visible(False) # Oculta línea superior
    ax.spines["right"].set_visible(False) # Oculta línea derecha
    
    plt.tight_layout()
    
    # Guardar la imagen del gráfico
    plt.savefig(GRAFICO_PNG, dpi=150)
    plt.close()

    # 4. Formatear la tabla para el Markdown (ocultando prompts largos si fuera necesario)
    df_tabla = df.copy()
    
    # Truncamos el system_prompt a 30 caracteres para que no deforme la tabla en Markdown
    if "system_promt" in df_tabla.columns:
        df_tabla["system_promt"] = df_tabla["system_promt"].apply(
            lambda x: (str(x)[:27] + "...") if len(str(x)) > 30 else str(x)
        )
    
    # Formateamos las columnas porcentuales
    df_tabla["precision"] = (df_tabla["precision"] * 100).round(1).astype(str) + "%"
    df_tabla["p_sin_respuesta"] = (df_tabla["p_sin_respuesta"] * 100).round(1).astype(str) + "%"
    df_tabla["p_mal_formadas"] = (df_tabla["p_mal_formadas"] * 100).round(1).astype(str) + "%"


    
    # Convertimos la fecha a string legible
    df_tabla["fecha"] = df_tabla["fecha"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 5. Construir y escribir el documento Markdown
    contenido_md = f"""# 📊 Reporte Histórico de Evaluaciones (Evals)

Última actualización: `{df_tabla['fecha'].iloc[-1]}`

## 📈 Tendencia de Precisión
![Evolución de Precisión]({GRAFICO_PNG.name})

---

## 📝 Historial de Ejecuciones Acumuladas

{df_tabla.to_markdown(index=False)}
"""

    # Guardar el archivo Markdown actualizado
    REPORTE_MD.write_text(contenido_md, encoding="utf-8")
    console.print(f"✓ Evaluación registrada. Reporte actualizado en: {REPORTE_MD.resolve()}")