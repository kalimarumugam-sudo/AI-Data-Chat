# AI Data Chat

A Streamlit dashboard with a sidebar AI assistant that lets you explore tabular data using natural language. Ask questions in plain English, and the app converts them to SQL, runs them against a local dataset, and updates the dashboard in real time.

## What it does

- **Interactive dashboard** — KPIs, charts, and a filterable data table
- **AI chat sidebar** — filter, sort, aggregate, and analyze data with natural language
- **Local CSV analysis** — DuckDB-powered SQL over an in-memory dataset (works out of the box)
- **Optional Oracle integration** — connect your own database for advanced queries (requires configuration)
- **Flexible LLM backend** — OpenAI GPT-4 (default) or AWS Bedrock Claude 3.5 Sonnet

## Sample data

This repository ships with **synthetic sample data** (`data/csv/sample_rates.csv`) representing fictional wholesale rate records. All destinations, suppliers, and values are fabricated for demonstration — no real business data is included.

| Column | Description |
|--------|-------------|
| Destination | Routing region |
| Supplier | Wholesale provider name |
| Supplier Product | Product offering from the supplier |
| Product | Product category |
| Rate / Floor Price | Pricing metrics |
| Volume | Traffic volume |
| Next Valid From / Until | Rate validity period |

## Quick start

### Prerequisites

- Python 3.9+
- An [OpenAI API key](https://platform.openai.com/api-keys)

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/AI-Data-Chat.git
cd AI-Data-Chat
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your API key:

```bash
OPENAI_API_KEY=sk-your-key-here
```

### 4. Run the app

```bash
streamlit run data_chat_app.py
```

Open the URL shown in the terminal (typically http://localhost:8501).

## Example queries

Try these in the sidebar chat:

- *Show top 5 suppliers by volume*
- *What is the average rate for North Region?*
- *Filter to Premium-Voice products only*
- *Show destinations where rate is greater than floor price*
- *Reset* — restore the full dataset

## Project structure

```
AI-Data-Chat/
├── data_chat_app.py          # Application entry point
├── src/
│   ├── frontend.py           # Streamlit UI (dashboard + chat)
│   ├── ai_service.py         # LLM integration and query routing
│   ├── data_loader.py        # CSV data loading
│   ├── database_tools.py     # Optional Oracle connection
│   └── schema_service.py     # Business dictionary support
├── config/                   # Database and AWS configuration
├── data/
│   ├── csv/sample_rates.csv  # Synthetic demo dataset
│   └── metadata/             # Business term mappings
├── resources/prompt.md       # AI system prompt template
└── requirements.txt
```

## LLM provider configuration

**OpenAI (default):** Set `OPENAI_API_KEY` in `.env`. No code changes needed.

**AWS Bedrock:** Edit `src/ai_service.py` — comment out the OpenAI block and uncomment the Bedrock block. Configure AWS credentials in `.env`.

## Optional: Oracle database

Oracle support is included for teams that want to query a live database alongside the local CSV. To enable it:

1. Set `ORACLE_USER`, `ORACLE_PASSWORD`, and `ORACLE_DSN` in `.env`
2. Customize `data/metadata/business_dictionary.json` for your schema
3. Ask questions that mention *database* or *oracle* in the chat

Without Oracle credentials, the app works fully in **CSV-only mode**.

## Using your own data

1. Replace `data/csv/sample_rates.csv` with your file (semicolon-separated)
2. Keep the same column headers, or update column references in `src/data_loader.py` and `src/frontend.py`
3. Restart the app

## Troubleshooting

| Issue | Fix |
|-------|-----|
| CSV not found | Ensure `data/csv/sample_rates.csv` exists |
| OpenAI errors | Verify `OPENAI_API_KEY` in `.env` |
| Oracle connection fails | Check DSN, credentials, and network access |
| Import errors | Run `pip install -r requirements.txt` |

## License

MIT License — see [LICENSE](LICENSE) for details.
