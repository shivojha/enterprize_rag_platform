# Mortgage RAG Platform — Documentation

> **Developer Machine Only** — This is a zero-cost POC running entirely on Docker Compose.
> No cloud accounts or API keys required.

---

## Documents

| Document | Description |
|---|---|
| [requirements.md](./requirements.md) | In-scope / out-of-scope requirements, constraints |
| [architecture.md](./architecture.md) | System architecture (Mermaid diagrams, tech stack) |
| [testing_plan.md](./testing_plan.md) | Manual and scripted tests, known limitations |
| [cloud_migration_free_tier.md](./cloud_migration_free_tier.md) | Next step: deploy to free cloud services ($0/month) |
| [azure_migration.md](./azure_migration.md) | Enterprise Azure stack with managed services and security |

---

## Quick Start

```bash
# 1. Start all services + pull Mistral model (~5 min, one-time)
bash setup.sh

# 2. Load demo loan data
bash load_demo_data.sh

# 3. Open UI
open http://localhost:5174

# 4. Run API tests
bash test_pipeline.sh
```

---

## Service URLs (local)

| Service | URL | Credentials |
|---|---|---|
| React UI | http://localhost:5174 | — |
| FastAPI docs | http://localhost:8002/docs | — |
| Qdrant dashboard | http://localhost:6334/dashboard | — |
| LangFuse | http://localhost:3002 | admin@mortgage.local / mortgage123 |

---

## Deployment Roadmap

```
Developer Machine (now)
        ↓
Free Cloud Tier — Railway, Neon, Qdrant Cloud, Groq, Vercel
        ↓
Azure Enterprise — Container Apps, Azure OpenAI, AI Search, Key Vault, APIM
```

See [cloud_migration_free_tier.md](./cloud_migration_free_tier.md) for the next step.
