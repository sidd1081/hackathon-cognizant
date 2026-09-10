# Deployment

Three supported ways to deploy:

- **A. Docker Compose** on a single host (EC2/Lightsail/local) — one command, same-origin, Postgres included.
- **B. Google Cloud Run** — the current live deployment. Backend + frontend each as a separate Cloud Run service, CI/CD via GitHub Actions.
- **C. Hugging Face Spaces (backend) + Vercel (frontend)** — free hosting, split origins.

---

## Live deployment (Cloud Run)

- **Frontend:** https://incident-rca-frontend-719419392728.us-central1.run.app
- **Backend:** https://incident-rca-api-thamtf7d5a-uc.a.run.app
- **GCP project:** `rcaasda` · region `us-central1`

---

## A. Docker Compose (single host)

The app ships as two containers wired together by Docker Compose:

- **backend** — FastAPI + Sentence-Transformers (MiniLM, baked in) + FAISS + Groq
- **web** — nginx serving the built React frontend and proxying `/api` to the backend

Everything is **same-origin** (nginx proxies `/api`), so there's no CORS setup and
the frontend needs no backend URL.

```
Browser ─▶ web (nginx :8080) ─┬─ /       → static frontend
                              └─ /api/*   → backend :8000 ─┬─ Groq API
                                             ./backend/data │  (FAISS index)
                                                            └─ Postgres (users)
```

The compose stack includes a **Postgres** service, so user accounts persist in a
named volume (`pgdata`). Locally without compose (bare `uvicorn`) the backend
falls back to a SQLite file (`data/auth.db`) when `DATABASE_URL` is unset.

## Prerequisites

- Docker + Docker Compose (v2)
- A Groq API key

## Run it (local or any VM)

```bash
# 1. Configure the backend (Groq key; set a strong JWT_SECRET for anything public)
cd backend
cp .env.example .env         # then edit .env: GROQ_API_KEY=..., JWT_SECRET=...
cd ..

# 2. Build and start
docker compose up --build          # add -d to run detached

# 3. Open the app
#    http://localhost:8080
```

On **first start** the entrypoint checks for the FAISS index — it is already
baked into the image at build time, so startup is instant. The check is a
fallback for local dev with a mounted volume that overrides the image's data.

Useful commands:

```bash
docker compose logs -f backend     # watch backend logs (incl. index build)
docker compose down                # stop
docker compose up --build -d       # rebuild + restart detached
```

## Configuration

Backend env comes from `backend/.env` (loaded via compose `env_file`):

| Variable | Notes |
|---|---|
| `GROQ_API_KEY` | **required** for RCA |
| `JWT_SECRET` | **set a long random value in production** (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `GROQ_MODEL` | default `openai/gpt-oss-20b` |
| `GROQ_MAX_RETRIES` | default `2` |
| `DATABASE_URL` | set by compose to Postgres (`postgresql://rca:rca@db:5432/rca`); unset → SQLite fallback |

Persisted state: the FAISS index in `./backend/data/` (bind-mounted) and **user
accounts in Postgres** (the `pgdata` named volume). Back both up if you care
about registered users; e.g. `docker compose exec db pg_dump -U rca rca > users.sql`.

## Deploying to AWS

This compose setup runs unchanged on a single VM:

1. **EC2 / Lightsail:** launch a `t3.medium` (2 vCPU / 4 GB — Torch needs ~2 GB),
   install Docker + Compose, clone the repo, create `backend/.env`, then
   `docker compose up --build -d`. Put it behind an ALB or Caddy/nginx for HTTPS,
   or open port 8080 via the security group for a quick demo.
2. **HTTPS:** terminate TLS at an ALB, or add a small Caddy/Traefik container in
   front of `web` for automatic Let's Encrypt certs.

> Users are stored in the compose **Postgres** service. For a managed database
> instead (RDS/Cloud SQL/Supabase/Neon), drop the `db` service and point
> `DATABASE_URL` at the managed instance — no code changes.

## Image notes

- **Backend image** is large (~2–3 GB) because it bundles PyTorch + the MiniLM
  weights. That's expected for local, GPU-free embeddings.
- The embedding model is baked at build time, so containers start without any
  HuggingFace download.
- Secrets are **never** baked into images — they're injected at runtime via
  compose `env_file`.

---

## B. Google Cloud Run

Cloud Run runs the backend container, scales to zero when idle (generous free
tier). The FAISS index and embedding model are baked into the image at build
time, so containers start instantly with no runtime embedding work.

### Prerequisites
- `gcloud` CLI installed and `gcloud auth login`
- A GCP project with billing enabled

### One-time setup
```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud config set builds/timeout 1800   # our build (~10 min) exceeds the 600s default
```

### Deploy backend

```bash
gcloud run deploy incident-rca-api \
  --source . \
  --region us-central1 \
  --memory 4Gi \
  --cpu 2 \
  --allow-unauthenticated \
  --set-env-vars "GROQ_API_KEY=<your_groq_api_key>,JWT_SECRET=<your_jwt_secret>,CORS_ORIGINS=<frontend_url>"
```

### Deploy frontend

```bash
gcloud run deploy incident-rca-frontend \
  --source ./frontend \
  --region us-central1 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60 \
  --allow-unauthenticated \
  --port 8080
```

The frontend has the backend URL hardcoded as a fallback in
`frontend/src/services/api.js`. To point it at a different backend, set
`VITE_API_BASE_URL` in `frontend/.env.production` before building.

### GitHub Actions CI/CD

Not included — deploy manually using the commands above.

### Notes
- **Cold starts:** the image is ~9 GB (PyTorch + baked FAISS index), so the first
  request after idle may take ~30–60 s to pull the image. Add `--min-instances 1`
  to keep one warm (small cost), or accept the cold start on the free tier.
- **Index baked in:** `preprocess` + `build_index` run during `docker build`, so
  the container starts instantly with no embedding work at runtime.
- **Durable users:** Cloud Run's filesystem is ephemeral — set `DATABASE_URL` to
  a managed Postgres (Cloud SQL, Supabase, or Neon) so accounts persist across
  redeploys. Without it the backend uses SQLite which resets on each deploy.
- **32 MB upload limit:** Cloud Run hard-rejects request bodies over 32 MB at the
  platform level. The app guards at 31 MB with a clear error message. The bundled
  dataset (34 MB) must be baked into the image (already done via the Dockerfile).
- **Better secrets:** for production, store `GROQ_API_KEY`/`JWT_SECRET` in Secret
  Manager and reference them with `--set-secrets` instead of `--set-env-vars`.

---

## C. Hugging Face Spaces (backend) + Vercel (frontend)

Free hosting. The backend runs as a Docker Space (HF free CPU: 2 vCPU / 16 GB,
enough for PyTorch); the frontend is a static Vercel deploy that calls the Space.
Because they're on different origins, the backend must allow the Vercel domain
via `CORS_ORIGINS`.

```
Vercel (frontend) ──HTTPS──▶ https://<user>-<space>.hf.space/api/*  (HF Space)
                                       └─ CORS_ORIGINS = your Vercel URL
```

### B1. Backend → Hugging Face Space

The **root `Dockerfile`** is backend-only and serves the API on port **7860**
(HF's default), with the MiniLM model and FAISS index baked in for instant boot.

1. Create a Space: <https://huggingface.co/new-space> → **SDK: Docker** → blank
   template → hardware **CPU basic (free)**.
2. Push this project to the Space's git repo (HF builds from the root
   `Dockerfile`). The Space's `README.md` must start with this metadata header —
   prepend it if pushing this repo's README:

   ```yaml
   ---
   title: AI Incident RCA Assistant API
   emoji: 🛠️
   colorFrom: indigo
   colorTo: blue
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```

   The 35 MB dataset must be tracked with **Git LFS** on the Space (HF requires
   LFS for files > 10 MB):

   ```bash
   git clone https://huggingface.co/spaces/<user>/<space> && cd <space>
   #   copy the project files in (or add the Space as a remote of this repo)
   git lfs install
   git lfs track "*.csv"
   git add .gitattributes .
   git commit -m "Deploy backend" && git push
   ```

3. In the Space → **Settings → Variables and secrets**, add:
   - `GROQ_API_KEY` — your Groq key *(secret)*
   - `JWT_SECRET` — a long random string *(secret)*
   - `CORS_ORIGINS` — your Vercel URL (set after B2; start with `*` if unsure)
   - `DATABASE_URL` — a managed Postgres URL for durable users (optional; see note)
4. The Space builds (~10 min: Torch + model + index) then serves at
   `https://<user>-<space>.hf.space`. Verify `…/api/health` and `…/docs`.

> Free Spaces have **ephemeral storage**: the index is baked into the image (always
> present), but without a database the SQLite **auth DB resets** on restart/rebuild.
> For durable users, set `DATABASE_URL` to a free managed Postgres (e.g. Supabase
> or Neon). Fine to skip for a short demo.

### B2. Frontend → Vercel

1. Vercel → **Add New → Project** → import the GitHub repo.
2. **Root Directory:** `frontend` (the included `frontend/vercel.json` sets the
   Vite build + SPA rewrites).
3. **Environment variable:** `VITE_API_BASE_URL = https://<user>-<space>.hf.space`
   (your Space URL, **no trailing slash**).
4. Deploy → you get `https://<app>.vercel.app`.

### B3. Wire them together (order matters)

1. Deploy the **backend Space** first → note its URL.
2. Deploy **Vercel** with `VITE_API_BASE_URL` = the Space URL.
3. Back in the Space, set `CORS_ORIGINS` = your Vercel URL → **Restart** the Space.
4. Open the Vercel URL, sign up, and analyze an incident.

If API calls fail with a CORS error in the browser console, `CORS_ORIGINS` on the
Space doesn't match the Vercel origin exactly (scheme + host, no trailing slash).
