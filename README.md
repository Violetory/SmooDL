# SmooDL

A smooth, extensible, API-first service for downloading the highest-quality images and videos from URLs across platforms.

SmooDL exposes a small action-oriented HTTP API for Shortcuts today and Web or CLI clients later. It delegates platform extraction to replaceable adapters, keeps media selection independent from extraction, and avoids transcoding by default.

## Current status

The repository contains the first server MVP:

- action-oriented RPC endpoints such as `POST /job/create`;
- asynchronous inspection and materialization jobs;
- YouTube and generic video extraction through `yt-dlp`;
- image collection extraction through `gallery-dl`;
- direct image downloading without re-encoding;
- local artifact storage, signed downloads, Range support, and SSE progress;
- extension points for extractors, selectors, stores, and storage backends.

See [the development plan](docs/development-plan.md) for the complete architecture and roadmap.

## Quick start

Prerequisites:

- Python 3.12+
- FFmpeg and ffprobe
- Deno 2.3+ for current YouTube extraction
- `yt-dlp` and `yt-dlp-ejs`
- `gallery-dl` for image-oriented platforms

Install the development environment with `uv`:

```bash
uv sync --extra media --group dev
```

Start the server:

```bash
uv run uvicorn smoodl.main:app --reload
```

Create a job:

```bash
curl -X POST http://127.0.0.1:8000/job/create \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://youtu.be/VIDEO_ID"}'
```

Run tests:

```bash
uv run pytest
```

Runtime data is written to `.data/` by default and is ignored by Git.

## Configuration

Environment variables use the `SMOODL_` prefix:

```text
SMOODL_DATA_DIR=.data
SMOODL_PUBLIC_BASE_URL=http://127.0.0.1:8000
SMOODL_SIGNING_SECRET=replace-this-in-production
SMOODL_API_KEY=
SMOODL_JOB_TIMEOUT_SECONDS=300
SMOODL_DOWNLOAD_TOKEN_TTL_SECONDS=3600
SMOODL_MAX_DOWNLOAD_BYTES=2147483648
SMOODL_YT_DLP_COOKIES_FILE=
SMOODL_GALLERYDL_COOKIES_FILE=
```

The in-memory job store is intended for the first local MVP. The documented production path replaces it with PostgreSQL/Redis without changing the public API or domain contracts.
