# Northwind Analyst Agent

**Northwind Analyst Agent** es un agente de inteligencia artificial de nivel empresarial especializado en analítica de datos (*Text-to-SQL*) e ingeniería de software modular. Este sistema actúa como un puente inteligente entre usuarios de negocio y un repositorio de datos masivo, abstrayendo la complejidad de las consultas técnicas mediante traducción precisa de lenguaje natural a código SQL optimizado y ejecutable en **PostgreSQL 17**.

---

### 📌 Estado del Proyecto & Contexto Académico
*Este repositorio constituye el **Trabajo Final integrador** para la aprobación de la **Certificación Profesional en AI Agentic Developer** dictada por el **ITBA (Instituto Tecnológico de Buenos Aires)**. Actualmente, el proyecto se encuentra **en desarrollo activo**, sirviendo como plataforma de consolidación progresiva para arquitecturas complejas de orquestación, gobernanza financiera de modelos, telemetría avanzada y patrones de diseño analíticos de vanguardia.*

---

## 🎯 Enfoque de Ingeniería
*Este repositorio no es un simple script de automatización ni un wrapper básico de APIs. Está diseñado desde cero bajo estándares de arquitectura limpia y patrones de diseño corporativos con un objetivo claro: demostrar las habilidades críticas de un **AI Agentic Developer Senior**.*

* **Diseño Orientado a la Producción (Production-Ready):** Separación absoluta de responsabilidades. Los clientes de modelos de lenguaje, el motor logístico de base de datos, la telemetría contable y las interfaces de visualización interactúan de manera desacoplada mediante abstracciones e inyección de dependencias.
* **Observabilidad y Gobernanza (FinOps):** Implementación nativa de auditoría de costos e interceptación transparente del ciclo de vida del agente. Ninguna llamada al modelo ocurre a ciegas; cada token de procesamiento cognitivo y de entrada/salida es rastreado, valorizado y controlado frente a políticas estrictas de presupuestos corporativos.
* **Resiliencia Estructural y Tolerancia a Fallas:** Manejo avanzado y granular de excepciones de bajo nivel para mitigar de forma proactiva las alucinaciones sintácticas de la IA, sentando las bases de la ingeniería para bucles autónomos de autocorrección (*Self-Healing*).
* **Portabilidad de Infraestructura:** Cero dependencias locales "mágicas". El entorno completo de datos, esquemas relacionales y dependencias se orquesta y automatiza herméticamente mediante contenedores Docker.

---

### ¿Qué permite hacer el sistema?
* **Análisis de Negocio bajo Demanda:** Permite a directores y analistas extraer KPIs comerciales (márgenes de ganancias, productos críticos, estacionalidad, métricas geográficas) sin depender de equipos de BI tradicionales.
* **Interoperabilidad de Modelos de Vanguardia:** Permite alternar dinámicamente el motor cognitivo de IA entre el SDK unificado de última generación de **Google Gemini** (capturando metadatos avanzados de razonamiento secuencial de la serie *Flash Thinking*) y **OpenAI** mediante configuraciones externas.
* **Control Presupuestario en Tiempo Real:** Bloquea ejecuciones y mitiga riesgos financieros si el consumo cumulativo de tokens del agente alcanza el límite financiero asignado (`BUDGET`).
* **Generación de Reportes Ejecutivos:** Compila de manera automática tabulaciones analíticas complejas e históricos de consumo mediante Pandas y genera gráficos estadísticos de área (`.png`) listos para auditorías directas de gerencia.

---

## 📊 Arquitectura del Data Mart Analítico (Northwind OLAP)

A diferencia del esquema tradicional de Northwind diseñado para operaciones transaccionales diarias (OLTP), este agente opera sobre una infraestructura optimizada de **Data Mart / Almacén de Datos (OLAP)**. El esquema relacional extraído de `system_prompt.txt` adopta un diseño multidimensional enfocado en Business Intelligence y consultas agregadas de alta performance:

### 1. Jerarquía de Dimensiones Geográficas (Snowflake Alignment)
El Data Mart normaliza las ubicaciones comerciales para habilitar análisis granulares de rendimiento por regiones geográficas:
* **`Continent`:** Entidad raíz que clasifica los continentes comerciales.
* **`Country`:** Almacena datos macroeconómicos esenciales como población (`Population`), capitales y códigos estandarizados, vinculados directamente a su respectivo continente.
* **`State`:** Modela subdivisiones políticas complejas, identificando tipos de estado, capitales internas y agrupaciones de regiones regionales de mercado (`RegionName`).
* **`City`:** Capa de granularidad final donde convergen los clientes y redes de distribución física.

### 2. Dimensión de Suministro y Catálogo Comercial
* **`Supplier`:** Estructura exhaustiva de socios comerciales mapeados directamente a la jerarquía geográfica (`CityKey`), registrando datos de contacto empresariales y canales de comunicación.
* **`Product`:** Entidad centralizada de inventario. Incorpora flags de control técnico estricto como `Discontinued`, implementado de manera nativa como tipo de dato de bajo nivel `bit` ('0' = Activo, '1' = Descontinuado), obligando al agente a procesar lógica binaria exacta en sus filtros analíticos.

### 3. Restricciones Técnicas y Reglas del Dominio SQL
El prompt del sistema (`system_prompt.txt`) dota al agente con el mapa mental exacto de restricciones y tipos primitivos de PostgreSQL:
* **Manejo Preciso de Datos Monetarios:** Las columnas financieras están estructuradas bajo el tipo nativo `money` de PostgreSQL. El agente está instruido estrictamente para realizar el casteo explícito de estos campos a `DECIMAL/FLOAT` antes de cualquier cálculo agregativo, eliminando errores de precisión matemática en tiempo de ejecución.
* **Filtros Flexibles y Resilientes:** Uso obligatorio de cláusulas `ILIKE` para mitigar discrepancias e inconsistencias de mayúsculas, minúsculas o acentuaciones dentro de las búsquedas de texto ejecutadas por el usuario.

---

## 🚀 Características Técnicas Principales

### 1. Multi-Provider Factory (Arquitectura Desacoplada)
Implementación del patrón de diseño Fábrica mediante la abstracción `LLMCliente`. La inicialización de componentes es dinámica e inyectada en tiempo de ejecución:
* **`GeminiClient`:** Desarrollado con el ecosistema de vanguardia `google-genai`. Extrae nativamente del conteo de metadatos de uso la telemetría cognitiva (`thoughts_token_count`), permitiendo medir el esfuerzo computacional invertido por los modelos de razonamiento avanzado.
* **`OpenAIClient`:** Desarrollado sobre el driver oficial de `openai`, parametrizado utilizando el rol moderno `developer` para maximizar la obediencia de las directivas analíticas y de sintaxis SQL.

### 2. Infraestructura Autogestionada en Docker
El ciclo de despliegue está 100% automatizado mediante **Docker Compose**:
* **`postgres_db`:** Contenedor aislado de PostgreSQL 17 configurado con volúmenes locales nombrados para asegurar la persistencia absoluta de los datos analíticos.
* **`db_initializer` (Contenedor Efímero):** Módulo basado en Python que monitoriza el estado de salud de la base de datos principal (`service_healthy`) y, al comprobar la disponibilidad del puerto, inicializa y ejecuta masivamente el esquema y los datos relacionales desde `northwind.sql` para luego cerrarse limpiamente sin desperdiciar recursos del host.

### 3. Pipeline de Datos Resiliente
El script `src/utils/database.py` envuelve la capa de ejecución con una red de seguridad fina y robusta basada en excepciones explícitas del driver `psycopg2`:
* **`OperationalError` / `DataError`:** Capturan fallas de red, credenciales o desajustes de tipos de datos.
* **`ProgrammingError`:** Captura de forma quirúrgica errores sintácticos u homónimos incorrectos de tablas/columnas causados por alucinaciones marginales de la IA. Actúa como el gancho de telemetría perfecto para implementar pipelines de autoreparación (*Self-Healing Inference*).
* **Purificador Sintáctico (`clean_sql_query`):** Pipeline lineal que remueve decoradores tipográficos de Markdown (` ```sql `), normaliza espaciados dobles y aplana saltos de línea para inyectar sentencias SQL puras de alta velocidad.

### 4. Telemetría Avanzada y Módulo Financiero (Tokenomics)
La lógica financiera es completamente transparente para el código core del negocio gracias al uso de programación orientada a aspectos mediante el decorador de diseño `@auditar_tokenomics`:
* **Auditoría Contable:** Registra timestamps de microsegundos, latencias exactas de respuesta, distribución de tokens y costos monetarios detallados en `artifacts/tokenomics_history.json`.
* **Visualización de Datos Corporativos:** Genera diagramas financieros ejecutivos (`artifacts/costo_acumulado.png`) automatizando el uso de Pandas y subplots de Matplotlib para proyectar el consumo vs presupuesto.
* **Reporte Ejecutivo:** Exportación dinámica del historial de llamadas mediante matrices de datos volcadas a tablas Markdown puras con `.to_markdown()`.

### 5. Interfaz Visual e Industrial (Rich Logging)
Salida de logs unificada en `src/utils/logger.py`:
* Descarte total de impresiones rudimentarias. Emplea `RichHandler` para proveer resaltado de sintaxis SQL en vivo sobre la terminal y renderizado visual avanzado de errores (`rich_tracebacks`).
* Persistencia dual: Filtro de nivel operativo `INFO` en consola para el usuario y volcado profundo de depuración `DEBUG` estructurado con timestamps en `logs/app.log`.

---

## 📂 Estructura de Archivos del Repositorio

```text
├── artifacts/                           # Reportes, telemetría y entregables visuales
│   ├── costo_acumulado.png             # Gráfica analítica de evolución del gasto vs presupuesto
│   ├── REPORTE_TOKENOMICS.md           # Reporte corporativo ejecutivo en formato Markdown
│   └── tokenomics_history.json         # Historial financiero cumulativo de tokens y latencias
├── logs/
│   └── app.log                          # Logs profundos del sistema (Nivel DEBUG plano)
├── src/                                 # Código fuente centralizado de la aplicación
│   ├── __init__.py
│   ├── core/                            # Núcleo analítico y orquestadores de IA
│   │   ├── __init__.py
│   │   └── llm/                         # Capa de abstracción y factoría de clientes LLM
│   │       ├── __init__.py              # Enrutador dinámico: get_llm_client()
│   │       ├── base.py                  # Definición de estructuras de datos e interfaces
│   │       ├── gemini.py                # Implementación bajo SDK google-genai unificado
│   │       └── openai.py                # Implementación con SDK oficial de OpenAI
│   └── utils/                           # Módulos transversales y utilidades del sistema
│       ├── __init__.py
│       ├── database.py                  # Manejo resiliente de queries y captura de excepciones
│       ├── decorators.py                # Decoradores contables y lógica de reintentos
│       ├── errors.py                    # Jerarquía de excepciones de dominio personalizado
│       ├── logger.py                    # Configuración central de Rich Logging unificado
│       ├── tokenomics.py                # Lógica contable, graficación y reporteo financiero
│       └── validators.py                # Validaciones estáticas de parámetros y prompts
├── .example.env                         # Plantilla e instrucciones de variables de entorno
├── database_init.py                     # Script independiente de control y poblado para Docker
├── docker-compose.yml                   # Configuración y orquestación del cluster de servicios
├── main.py                              # Orquestador e hilo conductor analítico del agente
└── system_prompt.txt                    # System prompt estricto con mapa completo del Data Mart
```

---

## ⚙️ Configuración del Entorno y Variables (.env)

Configura tu archivo `.env` en la raíz tomando como referencia el archivo `.example.env`:

```ini
# Selección del Core Cognitivo
LLM_PROVIDER=GEMINI                      # Opciones válidas: GEMINI | OPENAI
GEMINI_API_KEY=tu_api_key_aqui
GEMINI_MODEL=gemini-2.5-flash-thinking-exp 
OPENAI_API_KEY=tu_api_key_aqui
OPENAI_MODEL=gpt-4o

# Capa de Datos e Infraestructura Relacional
DB_USER=postgres
DB_PASSWORD=mi_password_secreto
DB_NAME=northwind_dw
DB_PORT=5432
DB_HOST=localhost                        # Cambiar a 'postgres_db' si se ejecuta dentro del clúster Docker

# Gestión Financiera y FinOps (Tokenomics)
BUDGET=5.0                               # Presupuesto límite global expresado en USD
GEMINI_INPUT_TOKENS_COST_PER_MILLION=0.075
GEMINI_OUTPUT_TOKENS_COST_PER_MILLION=0.30
OPENAI_INPUT_TOKENS_COST_PER_MILLION=2.50
OPENAI_OUTPUT_TOKENS_COST_PER_MILLION=10.00
```

---

## 🛠️ Instalación y Despliegue Secuencial

### Paso 1: Clonar y configurar variables de entorno
Ubica los archivos del agente en tu entorno local y duplica la plantilla de variables completando tus tokens de API:
```bash
cp .example.env .env
```

### Paso 2: Inicializar la Infraestructura de Datos (Docker)
Levanta los servicios contenerizados para automatizar la creación y poblado masivo del Data Mart analítico de Northwind:
```bash
docker compose up -d --build
```
*Este comando inicializará de manera asíncrona la base de datos de PostgreSQL y lanzará el contenedor de poblado automático. Al finalizar la inserción, el contenedor inicializador se detendrá de forma autónoma, liberando memoria.*

### Paso 3: Aislar el Entorno Virtual de Desarrollo
Crea y activa un entorno virtual limpio para gestionar las dependencias de Python:
```bash
# Inicialización
python -m venv env

# Activación en sistemas Unix (macOS/Linux)
source env/bin/activate

# Activación en Windows
env\Scripts\activate
```

Instala el set de dependencias empresariales del sistema:
```bash
pip install -r requirements.txt
```

### Paso 4: Ejecutar el Agente Analítico
Inicia el flujo interactivo de procesamiento de preguntas de negocio:
```bash
python main.py
```

---

## 🔄 Flujo Operativo Interno del Agente
1. **Inyección de Contexto:** El orquestador lee `system_prompt.txt` e inyecta al LLM las reglas de casteo monetario, tratamiento de banderas binarias y el diseño multidimensional del Data Mart.
2. **Instanciación Dinámica:** La factoría evalúa el proveedor configurado e inyecta la clase del cliente correspondiente.
3. **Inferencia Guardrailizada:** Por cada prompt de negocio enviado, el decorador calcula el costo real exacto, actualiza el archivo histórico JSON y verifica que no se viole el presupuesto global.
4. **Purificación e Inyección SQL:** La respuesta es limpiada de caracteres Markdown, enviada al driver de PostgreSQL con captura estricta de excepciones estructurales y procesada en DataFrames de Pandas.
5. **Renderizado e Interacción:** El pipeline de Rich pinta en consola la consulta analítica formateada y la tabla de resultados en color de alta fidelidad, pausando interactivamente para el análisis secuencial.
6. **Compilación de Reporte de Cierre:** Al finalizar la lista de prompts, el agente consolida las telemetrías y exporta el gráfico visual Matplotlib y el reporte ejecutivo Markdown automatizado.
