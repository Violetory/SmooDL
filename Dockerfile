ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG DENO_VERSION=2.9.6
ARG UV_VERSION=0.6.4
ARG DEBIAN_MIRROR=
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:/usr/local/bin:$PATH" \
    HOME=/data \
    DENO_DIR=/data/.cache/deno

RUN if [ -n "$DEBIAN_MIRROR" ]; then \
      sed -i "s|http://deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) deno_arch=x86_64 ;; \
      arm64) deno_arch=aarch64 ;; \
      *) echo "Unsupported architecture" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 --connect-timeout 15 --max-time 300 "https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-${deno_arch}-unknown-linux-gnu.zip" -o /tmp/deno.zip; \
    unzip /tmp/deno.zip -d /usr/local/bin; \
    rm /tmp/deno.zip; \
    deno --version

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra media --no-editable \
    && uv cache clean \
    && groupadd --gid 10001 smoodl \
    && useradd --uid 10001 --gid smoodl --home-dir /data --no-create-home smoodl \
    && mkdir -p /data \
    && chown -R smoodl:smoodl /data

USER smoodl
ENV SMOODL_DATA_DIR=/data
EXPOSE 8082
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/system/health', timeout=4)"]
# Jobs run inside this process; multiple workers need a shared job store first.
CMD ["uvicorn", "smoodl.main:app", "--host", "0.0.0.0", "--port", "8082", "--workers", "1"]
