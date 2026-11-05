# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONPATH=/app/services/api PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_NO_CACHE=1
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; uv sync --frozen --no-dev
COPY services ./services
COPY fixtures ./fixtures
RUN chmod -R a+rX /app/services /app/fixtures && useradd --uid 10001 --create-home app
USER app
CMD [".venv/bin/uvicorn","caseflow.main:app","--host","0.0.0.0","--port","8102"]
