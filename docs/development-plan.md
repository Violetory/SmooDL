# SmooDL development plan

## 1. Product definition

SmooDL is an API-first media inspection and download service. Its first client is an Apple Shortcut that submits a shared URL. Image posts return previewable assets for multi-selection; video posts are downloaded automatically. Future Web and CLI clients use the same API and domain model.

SmooDL promises the highest-quality representation currently exposed to the authorized user by a platform. It prefers an existing watermark-free representation and does not re-encode media by default. It does not promise to recover an upload master that a platform does not expose, remove watermarks from pixels, or bypass private, paid, DRM-protected, or otherwise inaccessible content.

## 2. Design decisions

- The public API is action-oriented JSON over HTTP RPC.
- Paths use `/{service}/{action}` and contain no `/api`, version prefix, or resource identifier.
- JSON parameters are carried in request bodies.
- Browser-native downloads and SSE use signed opaque query tokens because those transports require usable GET URLs.
- The server begins as a modular monolith with independent API, worker, and cleanup processes.
- Extracting candidates, selecting quality, downloading bytes, processing containers, and storing artifacts are separate responsibilities.
- Public schemas never expose raw `yt-dlp` or `gallery-dl` output.
- Breaking API changes are avoided. A future breaking version can be negotiated with a `SmooDL-API-Version` header rather than a URL prefix.

## 3. Supported platforms

The initial adapter set targets YouTube, TikTok, Instagram, X, Pinterest, and the video-oriented Xiaohongshu URLs already supported by `yt-dlp`. YouTube and general video posts use `yt-dlp`; image-oriented posts use `gallery-dl`. Dedicated Douyin, full Xiaohongshu image-note coverage, and Threads adapters are subsequent work because they require more platform-specific maintenance.

Support means best-effort extraction of public or user-authorized media. Platform changes can temporarily break an adapter, so each platform has independent health reporting and contract tests.

## 4. Architecture

```text
Shortcut / Web / CLI
          |
     HTTP RPC API
          |
      Job service
          |
   Extractor registry ------ yt-dlp / gallery-dl / custom adapters
          |
    Variant selector
          |
   Download materializer --- direct HTTP / yt-dlp / FFmpeg stream copy
          |
     Artifact storage ------ local / S3 / R2 / MinIO
```

The MVP runs background work with in-process asyncio tasks, an in-memory job store, and local storage. Interfaces isolate those choices so production can replace them with Redis-backed workers, PostgreSQL, and object storage.

## 5. Workflow and states

Creating a job moves through the following states:

```text
queued -> inspecting
              |-> awaiting_selection -> materializing -> completed
              |-> materializing ----------------------> completed
```

Terminal alternatives are `failed`, `cancelled`, and `expired`.

Inspection downloads metadata and preview candidates only. An image or mixed post waits for selected asset IDs. An all-video post materializes automatically. Materialization downloads selected representations, merges separate video/audio streams with stream copy when required, verifies the result, stores artifacts, and creates signed download URLs.

## 6. Public API

### Commands and queries

```text
POST /job/create
POST /job/get
POST /job/materialize
POST /job/cancel
POST /job/subscribe

POST /platform/list

POST /file/authorize

GET  /job/events?token=...
GET  /preview/download?token=...
GET  /file/download?token=...

GET  /system/health
GET  /system/version
```

`POST /job/create` accepts a URL, quality policy, watermark policy, and playlist flag. It returns a job ID immediately. `POST /job/get` is the polling endpoint used by Shortcuts. `POST /job/materialize` accepts a job ID and selected asset IDs. `POST /file/authorize` creates a short-lived download link.

The API uses stable machine-readable error codes including `UNSUPPORTED_URL`, `UNSUPPORTED_PLATFORM`, `AUTHENTICATION_REQUIRED`, `CONTENT_PRIVATE`, `REGION_RESTRICTED`, `CLEAN_VARIANT_UNAVAILABLE`, `DEPENDENCY_MISSING`, `EXTRACTOR_FAILED`, `FILE_TOO_LARGE`, `RATE_LIMITED`, and `INTERNAL_ERROR`.

## 7. Domain model

- `Job` owns lifecycle, options, a post, artifacts, and an optional error.
- `Post` is platform-neutral metadata and an ordered list of assets.
- `Asset` is one logical image, video, audio item, or thumbnail.
- `Variant` is one platform-provided representation with dimensions, codecs, bitrate, watermark state, headers, and a download strategy.
- `Artifact` is a materialized local or object-storage file with MIME type, size, hash, media properties, and transformation state.

Watermark state is `none`, `platform`, `creator`, or `unknown`. Transformation state is `none`, `remux`, or `transcode`. Transcoding is disabled by default.

## 8. Extractor contract

Each extractor implements `supports`, `normalize_url`, and `inspect`. Extractors return domain objects rather than tool-specific dictionaries. The registry resolves adapters by priority and can fall back when an adapter reports that it cannot handle a URL.

Platform extraction does not choose final quality. A selector applies policies such as `best_available`, `ios_compatible`, `prefer_mp4`, `audio_only`, and `metadata_only`, combined with `prefer_clean`, `require_clean`, or `allow_any` watermark behavior.

## 9. Media handling

Images are copied byte-for-byte from the selected source. The server validates file signatures, content type, size, dimensions when available, and SHA-256. Image libraries must not re-save originals.

Video selection prefers the best available video and audio streams. FFmpeg may merge or remux with stream copy, but SmooDL does not use video re-encoding by default. The highest-quality YouTube result may be AV1/VP9 plus Opus in MKV or WebM and should then be saved to Files. An `ios_compatible` policy can prefer an existing H.264/AAC MP4 representation without transcoding, potentially at lower quality.

Current YouTube extraction requires `yt-dlp`, `yt-dlp-ejs`, Deno, FFmpeg, and ffprobe. Public content is attempted without cookies. Optional per-user cookies and PO-token provider support belong behind encrypted credential and provider interfaces.

## 10. Security and privacy

- Accept only HTTP(S) URLs for registered platform domains.
- Reject localhost, private, link-local, multicast, and cloud metadata destinations.
- Revalidate redirects and resolved addresses for server-managed HTTP downloads.
- Run external tools without a shell, with timeouts and restricted working directories.
- Limit file size, duration, concurrency, redirects, and task lifetime.
- Sanitize filenames and keep writes inside a job-specific storage directory.
- Store API tokens as hashes and platform credentials encrypted; never log credentials, PO tokens, or signed CDN URLs.
- Use short-lived HMAC-signed opaque tokens for events, previews, and downloads.
- Automatically delete expired temporary data.

## 11. Repository structure

```text
SmooDL/
  docs/
  src/smoodl/
    api/             RPC routes and schemas
    domain/          stable models and enums
    extractors/      registry and adapters
    services/        orchestration, selection, download, tokens
    stores/          job-store interfaces and implementations
    storage/         artifact-storage interfaces and implementations
  tests/
  pyproject.toml
```

Future `apps/web`, `apps/cli`, and generated TypeScript/Python SDKs remain clients of the same server contract. The CLI may later implement a `LocalMediaService` behind the same client-facing interface.

## 12. Delivery milestones

1. Establish domain models, settings, stores, storage, RPC routes, and tests.
2. Deliver YouTube inspection and automatic highest-quality materialization.
3. Deliver gallery-based image inspection, preview selection, and byte-preserving downloads for Instagram, X, Pinterest, and TikTok.
4. Add authentication sessions, rate limiting, persistent jobs, distributed workers, and object storage.
5. Add dedicated Douyin, Xiaohongshu, and Threads adapters with fixtures and smoke tests.
6. Generate SDKs and build the Web and CLI clients.

## 13. MVP acceptance criteria

- A Shortcut can create and poll a job using JSON bodies.
- YouTube video jobs automatically produce a downloadable artifact.
- Supported image posts return ordered preview assets and accept multiple selected IDs.
- Original image responses are not re-encoded; video is not transcoded by default.
- Downloads support content length, content disposition, byte ranges, and short-lived authorization.
- Failures have stable error codes and do not crash the service.
- New platforms can be added through the extractor registry without changing API schemas.
- Unit tests cover state transitions, URL routing, token authorization, selection, and RPC endpoints.

## 14. Licensing and compliance

`yt-dlp` and its packaged components must be distributed with their applicable notices. `gallery-dl` is GPL-2.0-only and is kept behind a subprocess adapter; distribution of Docker images or a future bundled CLI requires a license review. SmooDL only handles content the user is authorized to save and does not bypass DRM, paywalls, or private access controls.
