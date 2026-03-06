# ReelEmpire-CoD-Pro

Production-ready FastAPI + Celery pipeline for high-volume faceless short-form generation using **silent self-recorded CoD B-roll** with standalone professional voiceover scripts in four broad audience topics:

- Man vs Women / Relationships / Heartbreak
- Finance
- Health
- Left vs Right

## 1) Project Folder Structure

```text
.
├── app/
│   ├── __init__.py                   # Package marker
│   ├── analytics.py                  # Metrics scoring + topic feedback loop logic
│   ├── config.py                     # Pydantic settings + env mapping
│   ├── dashboard.py                  # /dashboard endpoints + regenerate action
│   ├── database.py                   # SQLAlchemy engine/session
│   ├── main.py                       # FastAPI entrypoint + API routes
│   ├── models.py                     # SQLAlchemy schema (reels, variants, review, posting, metrics)
│   ├── scheduler.py                  # APScheduler service for recurring batch + posting jobs
│   ├── schemas.py                    # Pydantic request/response models
│   ├── script_generator.py           # Master prompt + Anthropic/Grok/Ollama fallback + virality scoring
│   ├── tasks.py                      # Celery generation, batch, regenerate, publish queue tasks
│   ├── uploader.py                   # S3 upload + platform posting adapters (Meta/TikTok/YouTube)
│   ├── video_editor.py               # FFmpeg wrapper for vertical render + centered subtitles + audio mix
│   ├── voiceover.py                  # ElevenLabs TTS + local fallback audio
│   └── workers.py                    # Celery app
├── alembic/
│   ├── env.py                        # Alembic environment config
│   ├── script.py.mako                # Alembic revision template
│   └── versions/
│       └── 20260306_0001_init.py     # Initial migration
├── data/
│   ├── clips/                        # Drop your own raw CoD clips here
│   ├── music/                        # Optional royalty-free tracks
│   └── output/                       # Rendered voiceovers + MP4 reels
├── docker-compose.yml                # api, worker, scheduler, rabbitmq, postgres, redis
├── Dockerfile                        # App image with FFmpeg + Python dependencies
├── .env.example                      # Full environment contract
├── alembic.ini                       # Alembic CLI config
├── requirements.txt                  # Python dependencies
└── README.md
```

## 2) docker-compose services

`docker-compose.yml` includes:

- `api` (FastAPI)
- `worker` (Celery worker)
- `scheduler` (APScheduler runner)
- `rabbitmq` (queue broker)
- `postgres` (database)
- `redis` (Celery result backend)

## 3) Environment Setup

1. Copy env file:

```bash
cp .env.example .env
```

2. Fill in API keys (`ANTHROPIC_API_KEY`, `GROK_API_KEY`, `ELEVENLABS_API_KEY`, AWS, platform tokens).
3. Put your **self-recorded CoD clips** into `data/clips/`.
4. Optional: add royalty-free tracks into `data/music/`.
5. Start stack:

```bash
docker compose up --build
```

## 4) Database Schema + Migrations

- ORM schema: `app/models.py`
- Initial migration: `alembic/versions/20260306_0001_init.py`

Run migrations:

```bash
docker compose exec api alembic upgrade head
```

## 5) Script Engine and Master Prompt

- Master prompt constant: `app/script_generator.py` as `MASTER_SCRIPT_PROMPT`
- `/test_script` endpoint defaults to 10 variants instantly.

Example:

```bash
curl -X POST http://localhost:8000/test_script \
  -H "Content-Type: application/json" \
  -d '{"count":10}'
```

Generation behavior:

- Randomly picks one of the 4 broad topics (unless forced)
- Builds 3 variants per reel (A/B/C styles)
- Scores with heuristic + LLM virality score blend
- Picks best variant for render

## 6) Video Editing (FFmpeg Wrapper)

`app/video_editor.py` renders:

- 9:16 output (`1080x1920`)
- Random 15-60s segment
- Center-screen subtitles (`x=(w-text_w)/2`, `y=(h-text_h)/2`)
- White text with black outline
- Voiceover + optional low-volume background music mix

## 7) Batch Generation Endpoint

`/generate_batch` can queue 50 reels instantly (default):

```bash
curl -X POST http://localhost:8000/generate_batch \
  -H "Content-Type: application/json" \
  -d '{"count":50}'
```

Supports up to `MAX_BATCH_SIZE` (`2000` by default).

## 8) Dashboard

Open:

- [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

Shows:

- recent reels
- status + virality score
- latest performance metrics
- topic performance feedback loop
- one-click **Regenerate Better Script**

## 9) Local Ollama Fallback

If cloud LLM keys are missing/unavailable, generator falls back:

1. Start Ollama locally with `llama3.1:405b`
2. Set `OLLAMA_BASE_URL` and `SCRIPT_MODEL_LOCAL`
3. Scripts still generate through `/test_script` and batch tasks

## 10) Posting & Queueing

- Uses official APIs adapters in `app/uploader.py` for Meta Graph, TikTok, YouTube v3
- Human review queue is enabled by `REVIEW_REQUIRED=true`
- Approved reels are queued into per-account publishing jobs

## 11) Account Safety Strategy

Operational safeguards implemented:

- human review before publish (default)
- official platform APIs only
- staggered scheduling with minimum gaps
- per-account daily limits
- account health-score-aware queueing
- optional enterprise proxy hook (`PLATFORM_PROXY_URL`) if your network requires it

## 12) Cost Estimate (1000 reels/day)

Approximate monthly envelope (depends on script length and region):

- LLM scripts (3 variants/reel): high four-figure to low five-figure USD/month
- ElevenLabs voice: low to mid five-figure USD/month at full volume
- Compute/render/storage (ECS + S3 + DB + queues): mid four-figure USD/month
- Total typical range: **~$18k to $45k/month** at 1000/day

Tune cost by:

- reducing variants from 3 to 2 for lower tiers
- adding cached templates for low-performing windows
- auto-pausing underperforming topics via feedback loop

## 13) Scaling to AWS ECS

Recommended production layout:

- ECS/Fargate service for `api`
- ECS/Fargate workers with autoscaling on RabbitMQ queue depth
- RDS Postgres + ElastiCache Redis + Amazon MQ RabbitMQ (or self-managed)
- S3 lifecycle policies for raw/output media
- CloudWatch alarms on queue lag, failure rate, watch-time degradation

## 14) Legal Notes

- Use only gameplay you recorded or fully licensed.
- Keep output meaningfully transformative (new narration, educational/commentary framing, custom subtitles/editing).
- Follow each platform's developer terms, content policies, and automation rules.
- This project is technical infrastructure, not legal advice.

## 15) Core API Routes

- `GET /health`
- `POST /test_script` (default 10 script variations)
- `POST /generate_batch` (default 50)
- `GET /reels`
- `POST /review/{reel_id}/decision`
- `GET /dashboard`
- `POST /dashboard/regenerate/{reel_id}`
- `GET /prompt`
