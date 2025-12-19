# SalesSwarm-Agentic

Multi-agent sales automation system powered by LLM.

## Overview

SalesSwarm-Agentic provides agentic capabilities for:
- **Lead Enrichment** - Extract data from LinkedIn profiles
- **Lookalike Finding** - Find similar leads based on ICP
- **Email Generation** - Create personalized email sequences
- **Lead Qualification** - Score leads against criteria
- **Company Intelligence** - Scrape and analyze company websites
- **Follow-up Orchestration** - Manage email sequence timing

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the server
python api_server.py
# Or with uvicorn
uvicorn api_server:app --reload --port 8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/leads/enrich` | POST | Enrich leads from LinkedIn URLs |
| `/api/leads/lookalike` | POST | Find lookalike leads |
| `/api/leads/qualify` | POST | Qualify and score leads |
| `/api/emails/generate` | POST | Generate email sequences |
| `/api/company/intel` | POST | Get company intelligence |
| `/api/campaigns/process` | POST | Process campaign with leads |

## Architecture

```
Frontend → SalesSwarm-Backend → SalesSwarm-Agentic → LLM
                                      ↓
                              [Agent Swarm]
                              ├── Email Generator
                              ├── Lead Qualification
                              ├── Lead Enrichment
                              ├── Company Intel
                              ├── Lookalike Finder
                              ├── Follow-up Orchestrator
                              └── CRM Sync
```

## Configuration

Set these in your `.env`:

```
OPENAI_API_KEY=sk-your-key
REDIS_URL=redis://localhost:6379
BACKEND_API_URL=http://localhost:5000
APIFY_API_KEY=your-apify-key  # For LinkedIn scraping
```

## License

MIT
