import functools
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Any
import matplotlib.pyplot as plt

logger = logging.getLogger("agent_logger.tokenomics")

PRESUPUESTO_MAXIMO = 1.50  # Límite en USD
COSTOS_MODELOS = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00}
}

# Carpetas donde se guardará todo de forma ordenada
REGISTRO_JSON = Path("artifacts/tokenomics_history.json")
GRAFICO_PNG = Path("artifacts/costo_acumulado.png")
REPORTE_MD = Path("artifacts/REPORTE_TOKENOMICS.md")

def auditar_tokenomics(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorador simple que registra la llamada en el JSON histórico (Igual que antes)"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        respuesta = func(*args, **kwargs)
        
        model = getattr(respuesta, "model", "gemini-2.5-flash")
        input_tokens = getattr(respuesta, "input_tokens", 0)
        output_tokens = getattr(respuesta, "output_tokens", 0)
        latencia_ms = getattr(respuesta, "latencia", 0.0)
        
        tarifas = COSTOS_MODELOS.get(model, COSTOS_MODELOS["gemini-2.5-flash"])
        costo = ((input_tokens / 1_000_000) * tarifas["input"]) + ((output_tokens / 1_000_000) * tarifas["output"])
        
        ahora = datetime.now()
        datos = {
            "timestamp": ahora.isoformat(),
            "fecha": ahora.strftime("%Y-%m-%d"),
            "hora": ahora.strftime("%H:%M"),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latencia_ms": latencia_ms,
            "costo": costo
        }
        
        # Persistir en el JSON histórico
        REGISTRO_JSON.parent.mkdir(parents=True, exist_ok=True)
        historial = json.loads(REGISTRO_JSON.read_text(encoding="utf-8")) if REGISTRO_JSON.exists() else []
        historial.append(datos)
        REGISTRO_JSON.write_text(json.dumps(historial, indent=2), encoding="utf-8")
        
        print(f"🪙 [Tokenomics] {model} | Costo: ${costo:.5f} USD")
        return respuesta
    return wrapper

def generar_reporte_markdown():
    """Genera el gráfico PNG con Matplotlib y escribe el archivo .md final sin tocar HTML"""
    if not REGISTRO_JSON.exists():
        print("No hay datos para reportar.")
        return

    historial = json.loads(REGISTRO_JSON.read_text(encoding="utf-8"))
    
    # 1. PROCESAR AGREGADOS MÁTEMÁTICOS
    total_input = sum(c["input_tokens"] for c in historial)
    total_output = sum(c["output_tokens"] for c in historial)
    total_costo = sum(c["costo"] for c in historial)
    presupuesto_restante = max(0.0, PRESUPUESTO_MAXIMO - total_costo)
    avg_latencia = sum(c["latencia_ms"] for c in historial) / len(historial)

    # 2. GENERAR EL GRÁFICO CON MATPLOTLIB Y GUARDARLO COMO PNG
    costos_por_dia = {}
    for c in historial:
        costos_por_dia[c["fecha"]] = costos_por_dia.get(c["fecha"], 0.0) + c["costo"]
    
    dias = sorted(costos_por_dia.keys())
    valores_acumulados = []
    acumulado = 0.0
    for d in dias:
        acumulado += costos_por_dia[d]
        valores_acumulados.append(acumulado)

    plt.figure(figsize=(7, 3.5))
    plt.fill_between(dias, valores_acumulados, color="#ebf8ff", alpha=0.7)
    plt.plot(dias, valores_acumulados, color="#3182ce", stroke_width=2, marker='o', label="Costo Acumulado")
    plt.axhline(y=PRESUPUESTO_MAXIMO, color='#e53e3e', linestyle='--', label="Presupuesto Máximo")
    plt.title("Evolución del Gasto vs Presupuesto")
    plt.ylabel("USD ($)")
    plt.legend(loc="upper left")
    plt.tight_layout()
    
    # Guardamos la imagen físicamente en la carpeta artifacts/
    plt.savefig(str(GRAFICO_PNG), dpi=150)
    plt.close()

    # 3. ESCRIBIR EL ARCHIVO MARKDOWN (.md) USANDO TEXTO PLANO
    with open(REPORTE_MD, "w", encoding="utf-8") as f:
        f.write(f"# Reporte Ejecutivo de Tokenomics y Telemetría\n")
        f.write(f"**Fecha de generación:** {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")
        f.write(f"Este reporte consolida los costos financieros y el consumo cognitivo de nuestros agentes de IA.\n\n")
        
        f.write(f"## Resumen General de Consumo\n\n")
        # Tabla en formato Markdown (¡Súper simple, sin código raro!)
        f.write(f"| Métrica de Control | Valor Acumulado |\n")
        f.write(f"| :--- | :--- |\n")
        f.write(f"| **Presupuesto Máximo Asignado** | ${PRESUPUESTO_MAXIMO:.4f} USD |\n")
        f.write(f"| **Costo Financiero Incurrido** | ${total_costo:.4f} USD |\n")
        f.write(f"| **Presupuesto Restante** | ${presupuesto_restante:.4f} USD |\n")
        f.write(f"| Tokens Totales Consumidos | {total_input + total_output:,} tokens |\n")
        f.write(f"| Latencia Promedio de API | {avg_latencia:,.2f} ms |\n\n")

        f.write(f"## Monitoreo Visual del Presupuesto\n\n")
        # Insertar la imagen en Markdown de forma nativa
        f.write(f"![Gráfica de Costo Acumulado](./costo_acumulado.png)\n\n")

        f.write(f"## Anexo: Historial de Llamadas Detallado\n\n")
        f.write(f"| # | Fecha | Hora | Modelo | Input | Output | Costo Llamada | Costo Acumulado |\n")
        f.write(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        
        costo_acum_seq = 0.0
        for idx, c in enumerate(historial, 1):
            costo_acum_seq += c["costo"]
            f.write(f"| {idx} | {c['fecha']} | {c['hora']} | {c['model']} | {c['input_tokens']:,} | {c['output_tokens']:,} | ${c['costo']:.5f} | ${costo_acum_seq:.5f} |\n")

    print(f"✓ ¡Reporte Markdown creado con éxito en: {REPORTE_MD}!")