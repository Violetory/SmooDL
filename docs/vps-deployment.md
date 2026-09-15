# VPS deployment with Docker Compose

The image contains Python 3.12, FFmpeg/ffprobe, Deno, yt-dlp, gallery-dl and
the SmooDL API. The asynchronous job worker currently runs inside the API process.
Run one replica with one Uvicorn worker until the in-memory job store is replaced
with shared storage.

## Configuration

Copy `deploy/compose.env.example` to `.env`. Set `SMOODL_SIGNING_SECRET` and
`SMOODL_API_KEY` to separate random values, for example using
`openssl rand -hex 32`. Keep `.env` private (`chmod 600 .env`). Set
`SMOODL_PUBLIC_BASE_URL` to the externally reachable HTTPS URL.

The Compose service publishes port 8082 on the VPS loopback interface. Public
requests enter through the reverse proxy on ports 80/443. There is no need to
open 8082 to the Internet. The `downloads` named volume is mounted at `/data`
and holds artifacts, working files and Deno cache. The container runs as UID
10001, and a new named volume inherits the image's directory ownership.

## New VPS: Caddy

Point the domain's A record at the VPS IP, allow TCP 80 and 443, then run:

```sh
docker compose --profile https up -d --build
docker compose ps
```

Caddy obtains and renews a public HTTPS certificate. Its certificate and state
directories also use named volumes. Use this profile only when ports 80/443
are available. If a DNS proxy is enabled, use an end-to-end HTTPS mode.

## VPS with an existing Nginx Proxy Manager

Use your VPS IP and a deployment directory such as `/opt/smoodl`.

The existing Nginx Proxy Manager container owns ports 80/443. Join its existing
`npm_default` network rather than start Caddy:

```sh
cd /opt/smoodl
docker compose -f compose.yaml -f deploy/compose.npm.yaml up -d --build
```

For this VPS, `deploy/nginx-smoodl.conf` uses the existing wildcard Cloudflare
Origin certificate at `/data/custom_ssl/npm-15/`. Install it on the host at
`/opt/npm/data/nginx/custom/smoodl.conf`, and include it once from
`/opt/npm/data/nginx/custom/http.conf`:

```nginx
include /data/nginx/custom/smoodl.conf;
```

Validate and reload without restarting the existing websites:

```sh
docker exec npm-app-1 nginx -t
docker exec npm-app-1 nginx -s reload
```

This is an Nginx custom configuration, so it does not appear as a proxy-host
entry in the Nginx Proxy Manager UI. It resolves the `smoodl-api` Docker alias
dynamically and disables response buffering for SSE and streamed downloads.

Cloudflare DNS: proxied A record `smoodl` → `<VPS_PUBLIC_IP>`. Keep HTTPS enabled
between Cloudflare and the VPS; the Origin certificate is intended for that
connection. No Cloudflare Tunnel is used.

If Docker Hub cannot be reached from this VPS, the already-used registry mirror
can supply the base image without changing the Dockerfile:

```sh
PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim-bookworm \
DEBIAN_MIRROR=https://mirrors.aliyun.com \
  docker compose -f compose.yaml -f deploy/compose.npm.yaml build
docker compose -f compose.yaml -f deploy/compose.npm.yaml up -d --no-build
```

The deployed VPS `.env` stores these mirror overrides so later builds use the
same sources without repeating the command-line variables.

If the VPS cannot download Python dependencies reliably, build the Linux amd64
image on a machine with working package access and transfer it over SSH:

```sh
docker build --platform linux/amd64 -t smoodl:local .
docker save smoodl:local | gzip | ssh myserver 'gunzip | docker load'
ssh myserver 'cd /opt/smoodl && docker compose -f compose.yaml -f deploy/compose.npm.yaml up -d --no-build'
```

This only builds the image locally; the service runs on the VPS. Transfer the
updated source and Compose files separately when deploying a new release.

## Operations

```sh
# Configure the myserver alias and private key in your local ~/.ssh/config.
ssh myserver
cd /opt/smoodl
docker compose -f compose.yaml -f deploy/compose.npm.yaml ps
docker compose -f compose.yaml -f deploy/compose.npm.yaml logs --tail=100 smoodl
curl -fsS http://127.0.0.1:8082/system/health
```

The API uses `Authorization: Bearer <SMOODL_API_KEY>` for protected RPC calls. An optional `SMOODL_SHORTCUT_API_KEY` is accepted with the same access and can be rotated independently; Compose loads it from `.env`. After changing a key, recreate the service with the same Compose files. The Shortcut asks for this key during import, and the shared template remains empty. The NPM configuration redirects `/install` to the current iCloud release.
The container restarts automatically with Docker. A restart preserves files in
the download volume, but clears the current in-memory job and artifact metadata;
existing jobs and download links cannot be recovered from files alone. Avoid
`docker compose down -v` unless deleting the stored downloads is intended.

Redis, PostgreSQL, object storage and a separate worker are future additions.
Platform cookies can be mounted read-only and configured through the existing
cookie-file environment variables; they are never included in the image.


### Application-only update on 2026-09-16

The Shortcut-key release reuses the deployed runtime and installs the rebuilt application wheel without downloading dependencies. The local and server `uv.lock` hashes matched. The server build context is `/opt/smoodl/.data/shortcut-release`; the rollback image is `smoodl:before-shortcut-key`. Runtime image `smoodl:local` now points to the updated image. The main API key and signing secret are unchanged. A future full build uses the repository Dockerfile as usual. Local Docker Desktop remained stopped during this update.
