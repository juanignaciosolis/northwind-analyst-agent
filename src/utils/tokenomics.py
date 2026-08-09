import logging
from logging import Logger

logger: Logger = logging.getLogger(__name__)


import functools
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Any
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.pyplot as plt
import os
from src.settings import settings


PRESUPUESTO_MAXIMO = settings.budget

REGISTRO_JSON = Path("artifacts/tokenomics_history.json")
GRAFICO_PNG = Path("artifacts/costo_acumulado.png")
REPORTE_MD = Path("artifacts/REPORTE_TOKENOMICS.md")
PDF_OUTPUT = Path("artifacts/REPORTE_TOKENOMICS.pdf")


def generar_reporte_markdown():
    if not REGISTRO_JSON.exists():
        logger.warning("No hay datos históricos registrados.")
        return

    df = pd.read_json(REGISTRO_JSON)

    total_input = df["input_tokens"].sum()
    total_output = df["output_tokens"].sum()
    total_input_costo = df["costo_input"].sum()
    total_output_costo = df["costo_output"].sum()
    total_costo = df["costo_total"].sum()
    avg_latencia = df["latencia_ms"].mean()

    presupuesto_restante = max(0.0, PRESUPUESTO_MAXIMO - total_costo)

    df_diario = df.groupby("fecha")["costo_total"].sum().cumsum().reset_index()

    # 4. GRAFICAR CON MATPLOTLIB USANDO LOS DATOS DE PANDAS
    plt.figure(figsize=(7, 3.5))
    plt.fill_between(df_diario["fecha"], df_diario["costo_total"], color="#ebf8ff", alpha=0.7)
    plt.plot(df_diario["fecha"], df_diario["costo_total"], color="#3182ce", linewidth=2, marker='o', label="Costo Acumulado")
    plt.axhline(y=PRESUPUESTO_MAXIMO, color='#e53e3e', linestyle='--', label="Presupuesto Máximo")
    plt.title("Evolución del Gasto vs Presupuesto")
    plt.ylabel("USD ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(str(GRAFICO_PNG), dpi=150)
    plt.close()


    df["costo_acumulado"] = df["costo_total"].cumsum()
    
    df_visible = df.copy()
    df_visible["input_tokens"] = df_visible["input_tokens"].map("{:,}".format)
    df_visible["output_tokens"] = df_visible["output_tokens"].map("{:,}".format)
    df_visible["costo_input"] = df_visible["costo_input"].map("${:.5f}".format)
    df_visible["costo_output"] = df_visible["costo_output"].map("${:.5f}".format)
    df_visible["costo_total"] = df_visible["costo_total"].map("${:.5f}".format)
    df_visible["costo_acumulado"] = df_visible["costo_acumulado"].map("${:.5f}".format)

    with open(REPORTE_MD, "w", encoding="utf-8") as f:
        f.write(f"# Reporte Ejecutivo de Tokenomics y Telemetría\n")
        f.write(f"**Fecha de generación:** {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")
        
        f.write(f"## Resumen General de Consumo\n\n")
        f.write(f"| Métrica de Control | Valor Acumulado |\n")
        f.write(f"| :--- | :--- |\n")
        f.write(f"| **Presupuesto Máximo Asignado** | ${PRESUPUESTO_MAXIMO:.4f} USD |\n")
        f.write(f"| **Costo Financiero Incurrido** | ${total_costo:.4f} USD |\n")
        f.write(f"| **Presupuesto Restante** | ${presupuesto_restante:.4f} USD |\n")
        f.write(f"| Tokens Totales Consumidos | {total_input + total_output:,} tokens |\n")
        f.write(f"| Latencia Promedio de API | {avg_latencia:,.3f} ms |\n\n")

        f.write(f"## Monitoreo Visual del Presupuesto\n\n")
        f.write(f"![Gráfica de Costo Acumulado](./costo_acumulado.png)\n\n")

        f.write(f"## Anexo: Historial de Llamadas Detallado\n\n")
        # TRUCO SUPREMO: Pandas convierte todo el DataFrame a una tabla Markdown real en UN solo comando
        # Seleccionamos solo las columnas interesantes para la tabla
        columnas_reporte = ["fecha", "hora", "provider", "model", "input_tokens", "output_tokens", "costo_total", "costo_acumulado"]
        tabla_md = df_visible[columnas_reporte].to_markdown(index=True)
        f.write(tabla_md)
        
    logger.info(f"[green]✓[/green] Reporte generado con éxito en: [yellow]\"{REPORTE_MD.parent}\"[/yellow]")

def auditar_tokenomics(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorador simple que registra la llamada en el JSON histórico (Igual que antes)"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        respuesta = func(*args, **kwargs)

        respuesta = respuesta.result
        
        model = getattr(respuesta, "model")
        input_tokens = getattr(respuesta, "input_tokens", 0)
        output_tokens = getattr(respuesta, "output_tokens", 0)
        latencia_ms = getattr(respuesta, "latencia", 0.0)
        
        tarifas = {
            "input": settings.gemini_input_usd_per_million if settings.default_provider == "GEMINI" else settings.openai_input_usd_per_million,
            "output": settings.gemini_output_usd_per_million if settings.default_provider == "GEMINI" else settings.opneai_output_usd_per_million
        }
        
        costo_input = input_tokens * (tarifas["input"] / 1000000)
        costo_output = output_tokens* (tarifas["output"] / 1000000)
        costo_total = costo_input + costo_output
        
        ahora = datetime.now()
        datos = {
            "timestamp": ahora.isoformat(),
            "fecha": ahora.strftime("%Y-%m-%d"),
            "hora": ahora.strftime("%H:%M"),
            "provider": settings.default_provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "costo_input": costo_input,
            "costo_output": costo_output,
            "costo_total": costo_total,
            "latencia_ms": latencia_ms
        }
        
        REGISTRO_JSON.parent.mkdir(parents=True, exist_ok=True)
        historial = json.loads(REGISTRO_JSON.read_text(encoding="utf-8")) if REGISTRO_JSON.exists() else []
        historial.append(datos)
        REGISTRO_JSON.write_text(json.dumps(historial, indent=2), encoding="utf-8")
        
        logger.info(
    f"┌─── [[bold blue] TELEMETRÍA LLM [/]] ────────────────────────────────────────\n"
    f"│ 🤖 Modelo:    {model} ({settings.default_provider})\n"
    f"│ ⏱️ Latencia:  {latencia_ms:,.2f} ms\n"
    f"├─ Tokens ────────────────────────────────────────────────────\n"
    f"│ 📥 Input:     {input_tokens:,} tokens\n"
    f"│ 📤 Output:    {output_tokens:,} tokens\n"
    f"│ 📊 Total:     {input_tokens + output_tokens:,} tokens\n"
    f"├─ Finanzas ──────────────────────────────────────────────────\n"
    f"│ 💵 Costo In:  ${costo_input:.5f} USD\n"
    f"│ 💵 Costo Out: ${costo_output:.5f} USD\n"
    f"│ 💰 Total:     ${costo_total:.5f} USD\n"
    f"└─────────────────────────────────────────────────────────────"
)

        return respuesta
    
    return wrapper


