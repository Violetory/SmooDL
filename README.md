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
- a signed, source-controlled Apple Shortcut workflow under `shortcuts/`;
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

## VPS deployment

`Dockerfile` and `compose.yaml` package the API and its in-process worker with
FFmpeg, Deno, yt-dlp and gallery-dl. Downloads use a persistent Docker volume.
See [the VPS deployment guide](docs/vps-deployment.md) for configuration,
optional Caddy HTTPS, and integration with the existing Nginx Proxy Manager.

## Apple Shortcut

The Shortcut is compiled from source, with the production HTTPS endpoint embedded at release time. Install it from [smoodl.violetcho.tech/install](https://smoodl.violetcho.tech/install) and enter your API Key in the import setup field; the server URL is already configured. The shared template contains no credential.

```bash
shortcuts/build.sh https://download.example.com
```

See [the Shortcut documentation](shortcuts/README.md) for behavior, build requirements, and release guidance.

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

The in-memory job store is intended for the first local MVP. The documented production path replaces it with PostgreSQL/Redis without changing the public API or domain contracts. The VPS keeps API authentication enabled. An optional `SMOODL_SHORTCUT_API_KEY` gives the Shortcut a separately revocable credential alongside `SMOODL_API_KEY`. Users enter their key during import; the shared template must not embed a reusable secret.
