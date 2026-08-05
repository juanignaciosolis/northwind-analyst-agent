# Northwind Analyst Agent

**Northwind Analyst Agent** is an enterprise-grade AI agent specialized in data analytics (*Text-to-SQL*) and modular software engineering. This system acts as an intelligent bridge between business users and a large database, removing the complexity of technical queries by accurately translating natural language into optimized SQL code executable on **PostgreSQL 17**.

---

### 📌 Project Status & Academic Context
*This repository serves as the **Final Capstone Project** for completing the **AI Agentic Developer Professional Certification** at **ITBA (Instituto Tecnológico de Buenos Aires)**. Currently under **active development**, the project acts as a hands-on platform to build complex orchestration architectures, model financial governance, advanced telemetry, and modern analytical design patterns.*

---

## 🎯 Engineering Approach
*This repository is not a simple automation script or a basic API wrapper. It is built from scratch following clean architecture standards and software design patterns to demonstrate the key skills of a Senior **AI Agentic Developer**.*

* **Production-Ready Design:** Clear separation of concerns. Language model clients, database logic, cost telemetry, and visualization interfaces interact in a decoupled way using abstractions and dependency injection.
* **Observability & Governance (FinOps):** Built-in cost tracking and full visibility into the agent's execution loop. No model call happens blindly: every input, output, and reasoning token is tracked, priced, and controlled under strict budget limits.
* **Resilience & Fault Tolerance:** Fine-grained error handling to catch AI syntax errors proactively, laying the engineering foundation for autonomous self-healing loops.
* **Infrastructure Portability:** No local environment dependencies. The entire database, schema, and app environment are fully containerized and automated using Docker.

---

### Key System Capabilities
* **On-Demand Business Analytics:** Allows managers and analysts to query commercial KPIs (profit margins, top products, seasonality, regional metrics) without needing traditional BI support.
* **Multi-Model Flexibility:** Switch dynamically between **Google Gemini** (using its unified SDK and reasoning tokens tracking) and **OpenAI** via environment variables.
* **Real-Time Budget Control:** Blocks model execution and prevents unwanted API costs if cumulative token usage reaches the assigned budget limit (`BUDGET`).
* **Executive Reporting:** Automatically compiles analytical tables and cost histories using Pandas, and generates visual area charts (`.png`) for management reporting.

---

## 📊 Analytical Data Mart Architecture (Northwind OLAP)

Unlike the traditional Northwind schema designed for daily transactions (OLTP), this agent operates over an optimized **Data Mart / Data Warehouse (OLAP)**. The relational schema defined in `system_prompt.txt` uses a multidimensional design built for Business Intelligence and high-performance aggregate queries:

### 1. Geographic Hierarchy (Snowflake Schema)
The Data Mart normalizes location data to enable detailed regional analysis:
* **`Continent`:** Root entity classifying business continents.
* **`Country`:** Stores key macroeconomic data like population, capitals, and standardized codes linked to their continent.
* **`State`:** Models state/province subdivisions, including capital cities and regional market groups (`RegionName`).
* **`City`:** Final granularity level where customer and distribution data connect.

### 2. Supply & Commercial Catalog Dimension
* **`Supplier`:** Comprehensive supplier records mapped directly to the geographic hierarchy (`CityKey`).
* **`Product`:** Central inventory entity. Includes flags like `Discontinued`, stored as a `bit` data type ('0' = Active, '1' = Discontinued), forcing the agent to handle exact binary filtering.

### 3. Technical Constraints & SQL Rules
The system prompt (`system_prompt.txt`) equips the agent with strict PostgreSQL rules:
* **Precise Monetary Handling:** Financial columns use PostgreSQL's native `money` type. The agent is strictly instructed to explicitly cast these fields to `DECIMAL/FLOAT` before applying aggregate calculations to prevent runtime type errors.
* **Resilient Case-Insensitive Filtering:** Mandatory use of `ILIKE` to handle case variations and accents in user text queries.

---

## 🚀 Main Technical Features

### 1. Multi-Provider Factory (Decoupled Architecture)
Implementation of the Factory design pattern via the `LLMCliente` abstraction. Model selection is dynamic and injected at runtime:
* **`GeminiClient`:** Built with the `google-genai` SDK. Automatically captures reasoning token telemetry (`thoughts_token_count`) to track computational effort from reasoning models.
* **`OpenAIClient`:** Built using the official `openai` SDK, configured with the `developer` role to enforce SQL generation directives.

### 2. Self-Managed Docker Infrastructure
The deployment workflow is fully automated with **Docker Compose**:
* **`postgres_db`:** Isolated PostgreSQL 17 container with persistent named volumes.
* **`db_initializer` (Ephemeral Container):** Python module that waits for PostgreSQL to be healthy (`service_healthy`), populates the database schema and data from `northwind.sql`, and shuts down cleanly to save system resources.

### 3. Resilient Data Pipeline
The `src/utils/database.py` script wraps execution with exception handling using `psycopg2`:
* **`OperationalError` / `DataError`:** Catch network, credential, or data type mismatch issues.
* **`ProgrammingError`:** Specifically catches SQL syntax or column/table typos caused by LLM hallucinations, serving as telemetry hooks for self-healing loops.
* **SQL Sanitizer (`clean_sql_query`):** Strips Markdown formatting (` ```sql `), normalizes spaces, and flattens line breaks to send clean, executable SQL to the database.

### 4. Advanced Telemetry & FinOps Module (Tokenomics)
Financial and token metrics are handled transparently using an aspect-oriented design pattern with the `@auditar_tokenomics` decorator:
* **Cost Auditing:** Records microsecond timestamps, latency, token breakdowns, and estimated USD costs in `artifacts/tokenomics_history.json`.
* **Data Visualization:** Automatically plots cumulative spending vs. budget (`artifacts/costo_acumulado.png`) using Pandas and Matplotlib.
* **Executive Summary:** Generates Markdown tables (`.to_markdown()`) summarizing execution history.

### 5. Production-Grade Rich Logging
Unified logging system in `src/utils/logger.py`:
* Replaces basic prints with `RichHandler` to provide live SQL syntax highlighting in terminal and rich error tracebacks.
* Dual logging: clean `INFO` logs on the console and detailed `DEBUG` traces saved in `logs/app.log`.

---

## 📂 Repository File Structure

```text
├── artifacts/                           # Reports, telemetry, and visual output
│   ├── costo_acumulado.png             # Spending trend vs. budget chart
│   ├── REPORTE_TOKENOMICS.md           # Executive report in Markdown
│   └── tokenomics_history.json         # History of token usage, latency, and costs
├── logs/
│   └── app.log                          # Detailed system logs (DEBUG level)
├── src/                                 # Application source code
│   ├── __init__.py
│   ├── core/                            # AI logic and agent orchestrator
│   │   ├── __init__.py
│   │   └── llm/                         # LLM client abstractions and factory
│   │       ├── __init__.py              # Dynamic router: get_llm_client()
│   │       ├── base.py                  # Interfaces and base data structures
│   │       ├── gemini.py                # Google Gemini client implementation
│   │       └── openai.py                # OpenAI client implementation
│   └── utils/                           # Shared utility modules
│       ├── __init__.py
│       ├── database.py                  # Database connection and query execution
│       ├── decorators.py                # Tokenomics and retry decorators
│       ├── errors.py                    # Custom exception hierarchy
│       ├── logger.py                    # Rich logging configuration
│       ├── tokenomics.py                # Telemetry, reporting, and cost calculations
│       └── validators.py                # Input validation functions
├── .example.env                         # Environment variables template
├── database_init.py                     # Standalone database setup script for Docker
├── docker-compose.yml                   # Docker orchestration config
├── main.py                              # Main application orchestrator
└── system_prompt.txt                    # System prompt with Data Mart context

---

## ⚙️ Environment Setup (.env)

Configure your .env file in the project root using .example.env as a reference:

```ini
# Cognitive Engine Selection
LLM_PROVIDER=GEMINI                      # Valid options: GEMINI | OPENAI
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash-thinking-exp 
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o

# Database & Relational Infrastructure
DB_USER=postgres
DB_PASSWORD=my_secret_password
DB_NAME=northwind_dw
DB_PORT=5432
DB_HOST=localhost                        # Change to 'postgres_db' when running inside Docker

# FinOps & Cost Management (Tokenomics)
BUDGET=5.0                               # Global budget cap in USD
GEMINI_INPUT_TOKENS_COST_PER_MILLION=0.075
GEMINI_OUTPUT_TOKENS_COST_PER_MILLION=0.30
OPENAI_INPUT_TOKENS_COST_PER_MILLION=2.50
OPENAI_OUTPUT_TOKENS_COST_PER_MILLION=10.00
```

---

## 🛠️ Environment Setup (.env)

### Step 1: Clone and Configure Environment Variables
Copy the example environment file and add your API keys:
```bash
cp .example.env .env
```

### Step 2: Start Data Infrastructure (Docker)
Launch the containerized services to build and populate the Northwind Data Mart:
```bash
docker compose up -d --build
```
*This command starts PostgreSQL asynchronously and runs the initializer container. Once the data is inserted, the initializer container stops automatically to save resources.*

### Step 3: Set Up Python Virtual Environment
Create and activate a virtual environment:
```bash
# Create environment
python -m venv env

# Activate on Unix (macOS/Linux)
source env/bin/activate

# Activate on Windows
env\Scripts\activate
```

Install required dependencies:
```bash
pip install -r requirements.txt
```

### Step 4: Run the Analyst Agent
Run the main agent orchestrator:
```bash
python main.py
```

---

## 🔄 Internal Agent Workflow
1. **Context Injection**: The orchestrator reads system_prompt.txt and feeds the LLM with database rules (money casting, binary flags, and schema structure).
2. **Dynamic Client Instantiation**: The factory reads the active provider and instantiates the matching client class.
3. **Guardrailed Inference**: On every prompt, the @auditar_tokenomics decorator tracks execution costs, updates telemetry, and ensures the total budget isn't exceeded.
4. **SQL Sanitization & Execution**: The generated SQL is cleaned of Markdown, safely executed on PostgreSQL, and loaded into Pandas DataFrames.
5. **Rich Terminal Display**: Rich formats and displays both the SQL query and the resulting data table directly in the terminal.
6. **Final Report Generation**: Once all prompts finish, the system generates the Matplotlib spending chart and the Markdown tokenomics report.
