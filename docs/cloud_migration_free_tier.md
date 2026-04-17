# Cloud Migration Guide — Free Tier

> **Current state:** Developer machine (Docker Compose, all local).
> **Next step:** Deploy to cloud using free-tier services, zero recurring cost.
> **After that:** [Azure stack migration](./azure_migration.md)

---

## Mapping: Local → Free Cloud

| Local Service | Free Cloud Replacement | Why |
|---|---|---|
| FastAPI (Docker) | **Railway** or **Render** free tier | Deploys from GitHub, free 512 MB container |
| React UI (Vite) | **Vercel** or **Netlify** free tier | Static hosting, instant deploy |
| PostgreSQL (local) | **Neon** (serverless Postgres, free tier) | 3 GB storage, branching, no server |
| Redis (local) | **Upstash** Redis free tier | 10K requests/day, serverless |
| Qdrant (local) | **Qdrant Cloud** free tier | 1 GB cluster, managed |
| Celery worker | Same container on Railway/Render | Background worker dyno |
| Ollama + Mistral | **Groq** API free tier (llama3, mixtral) | ~14K tokens/min free, no GPU needed |
| LangFuse (local) | **LangFuse Cloud** free tier | Managed, no Postgres to maintain |
| Embeddings | **HuggingFace Inference API** free tier | Or keep local in container |

**Estimated cost: $0/month** (within free tier limits for a POC/demo)

---

## Architecture Change: Local → Free Cloud

```mermaid
flowchart TD
    subgraph Cloud_Free["Free Cloud Tier"]
        UI["Vercel\nReact UI"]
        API["Railway / Render\nFastAPI :8000"]
        WK["Railway / Render\nCelery Worker"]
        PG["Neon\nPostgreSQL (serverless)"]
        RD["Upstash\nRedis (serverless)"]
        QD["Qdrant Cloud\nVector DB (1 GB free)"]
        LLM["Groq API\nLlama3-8B or Mixtral-8x7B"]
        LF["LangFuse Cloud\nObservability"]
        EMB["HuggingFace\nEmbeddings API"]
    end

    UI -->|"HTTPS"| API
    API -->|"send_task"| RD
    RD -->|"dequeue"| WK
    WK -->|"upsert vectors"| QD
    WK -->|"UPDATE status"| PG
    WK -->|"embed"| EMB
    API -->|"vector search"| QD
    API -->|"INSERT query_log"| PG
    API -->|"generate answer"| LLM
    API -->|"trace + spans"| LF
```

---

## Step-by-Step Migration

### Step 1 — Replace Ollama with Groq API

Groq offers Llama 3 and Mixtral inference for free (no GPU needed).

**Changes in `api/pipeline.py`:**

```python
# Before (Ollama)
response = httpx.post(f"{OLLAMA_URL}/api/generate", json={
    "model": LLM_MODEL,
    "prompt": prompt,
    "stream": False,
    "options": {"num_thread": 4, "num_predict": 300, "temperature": 0.1},
}, timeout=120)
answer = response.json()["response"].strip()

# After (Groq)
from groq import Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
completion = client.chat.completions.create(
    model="llama3-8b-8192",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=300,
    temperature=0.1,
)
answer = completion.choices[0].message.content.strip()
```

Add to `api/requirements.txt`:
```
groq>=0.9.0
```

### Step 2 — Replace Local Postgres with Neon

1. Create free account at [neon.tech](https://neon.tech)
2. Create project `mortgage-rag`
3. Copy connection string: `postgresql://user:pass@ep-xxx.neon.tech/mortgage_rag?sslmode=require`
4. Run init SQL: `psql "CONNECTION_STRING" < docker/init.sql`

**Environment variable change:**
```bash
POSTGRES_URL=postgresql://user:pass@ep-xxx.neon.tech/mortgage_rag?sslmode=require
```

No code changes — psycopg2 works with Neon out of the box.

### Step 3 — Replace Local Redis with Upstash

1. Create free account at [upstash.com](https://upstash.com)
2. Create Redis database, region closest to API deployment
3. Copy `REDIS_URL` (format: `rediss://default:TOKEN@host:port`)

**Environment variable change:**
```bash
REDIS_URL=rediss://default:TOKEN@xxx.upstash.io:6379
```

Celery works with Upstash via `rediss://` (TLS). No code changes.

### Step 4 — Replace Local Qdrant with Qdrant Cloud

1. Create free account at [cloud.qdrant.io](https://cloud.qdrant.io)
2. Create free cluster (1 GB, 1 node)
3. Copy cluster URL and API key

**Environment variable changes:**
```bash
QDRANT_HOST=https://xxx.us-east4-0.gcp.cloud.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=your-api-key
```

**Code change in `api/main.py` and `worker/tasks.py`:**
```python
# Before
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# After
qdrant = QdrantClient(
    host=QDRANT_HOST,
    port=QDRANT_PORT,
    api_key=os.getenv("QDRANT_API_KEY"),
    https=True,
)
```

### Step 5 — Replace Local LangFuse with LangFuse Cloud

1. Create free account at [cloud.langfuse.com](https://cloud.langfuse.com)
2. Create project, copy public/secret keys

**Environment variable changes:**
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

No code changes — already reads from env.

### Step 6 — Deploy API + Worker to Railway

1. Push code to GitHub
2. Create [railway.app](https://railway.app) account (free tier: $5 credit/month, enough for POC)
3. New project → Deploy from GitHub → select `api/` folder
4. Set all environment variables in Railway dashboard
5. Repeat for `worker/` as a separate service

**`api/Dockerfile` already works as-is.** Railway auto-detects it.

Optional — add `railway.json` to root:
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE" },
  "deploy": { "startCommand": "uvicorn main:app --host 0.0.0.0 --port 8000" }
}
```

### Step 7 — Deploy UI to Vercel

```bash
cd ui
npx vercel --prod
```

Set environment variable in Vercel dashboard:
```
VITE_API_URL=https://your-api.railway.app
```

Update `ui/src/App.jsx` to use env var:
```js
const API = import.meta.env.VITE_API_URL || "http://localhost:8002";
```

---

## `.env` Template for Cloud Deployment

```bash
# api/.env (do NOT commit)
QDRANT_HOST=https://xxx.gcp.cloud.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=
POSTGRES_URL=postgresql://user:pass@ep-xxx.neon.tech/mortgage_rag?sslmode=require
REDIS_URL=rediss://default:TOKEN@xxx.upstash.io:6379
GROQ_API_KEY=
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com
EMBEDDING_MODEL=all-MiniLM-L6-v2
LLM_MODEL=llama3-8b-8192
```

---

## Free Tier Limits to Watch

| Service | Free Limit | Risk |
|---|---|---|
| Groq | 14,400 req/day, 30 req/min | Will throttle under rapid demo use |
| Neon | 3 GB storage, 1 compute unit | Scales to zero — first query after idle ~2s cold start |
| Upstash Redis | 10,000 commands/day | Celery heartbeats count — monitor usage |
| Qdrant Cloud | 1 GB vector storage | ~500K 384-dim vectors; enough for POC |
| Railway | $5/month credit | ~500 compute hours; keep worker sleeping when idle |
| Vercel | 100 GB bandwidth/month | Static hosting — unlikely to hit |
| LangFuse Cloud | 50K observations/month | Enough for demo; 1 query ≈ 3 observations |

---

## Checklist

- [ ] Groq API key created and tested
- [ ] Neon Postgres created, `init.sql` applied
- [ ] Upstash Redis created, connection string tested
- [ ] Qdrant Cloud cluster created, API key set
- [ ] LangFuse Cloud project created
- [ ] `api/pipeline.py` updated for Groq
- [ ] Qdrant client updated for `api_key` + `https=True`
- [ ] API deployed to Railway with all env vars set
- [ ] Worker deployed to Railway (separate service)
- [ ] UI deployed to Vercel with `VITE_API_URL` set
- [ ] `load_demo_data.sh` run against cloud API URL
- [ ] End-to-end query test passed on cloud

---

## Next: Azure Stack

See [azure_migration.md](./azure_migration.md) for the enterprise Azure deployment using:
- **Azure Container Apps** (API + Worker)
- **Azure Static Web Apps** (UI)
- **Azure Database for PostgreSQL Flexible Server**
- **Azure Cache for Redis**
- **Azure OpenAI Service** (GPT-4o replacing Groq)
- **Azure AI Search** (replacing Qdrant)
- **Application Insights** (replacing LangFuse)
