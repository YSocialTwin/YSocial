# syntax=docker/dockerfile:1
# YSocial image built from the same wheel as the desktop installer.
# Build (from the repository root):   docker build -f docker/Dockerfile -t ysocial .
# LLM servers and PostgreSQL are external services (see docker/compose.yml).

FROM python:3.12-slim AS builder
WORKDIR /src
RUN pip install --no-cache-dir build
COPY . /src
# Profile pictures (~490 MB) are not part of the wheel: downloaded on first run.
RUN python -m build --wheel --outdir /dist .

FROM python:3.12-slim
LABEL org.opencontainers.image.title="YSocial" \
      org.opencontainers.image.source="https://github.com/YSocialTwin/YSocial" \
      org.opencontainers.image.description="YSocial social media digital twin"
# git: plugins (YServer/YClient/...) are installed from their repositories
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /dist/*.whl /tmp/
# Optional toxicity detection (detoxify + torch, large):  --build-arg WITH_TOXICITY=1
ARG WITH_TOXICITY=0
RUN set -eux; whl="$(ls /tmp/ysocial-*.whl)"; \
    if [ "$WITH_TOXICITY" = "1" ]; then \
      pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        "ysocial[toxicity] @ file://${whl}"; \
    else \
      pip install --no-cache-dir "${whl}"; \
    fi; \
    rm -f /tmp/ysocial-*.whl

ENV YSOCIAL_HOME=/data \
    YSOCIAL_HOST=0.0.0.0 \
    YSOCIAL_PORT=5000
VOLUME ["/data"]
EXPOSE 5000
COPY docker/entrypoint.sh /usr/local/bin/ysocial-entrypoint
RUN chmod +x /usr/local/bin/ysocial-entrypoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD curl -fsS "http://localhost:${YSOCIAL_PORT}/login" >/dev/null || exit 1
ENTRYPOINT ["ysocial-entrypoint"]
