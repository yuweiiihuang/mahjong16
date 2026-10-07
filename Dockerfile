FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM python:3.13-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /app/.venv /app/.venv
COPY app/ app/
COPY domain/ domain/
COPY bots/ bots/
COPY ui/ ui/
COPY configs/ configs/
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.web", "--host", "0.0.0.0", "--port", "8000", "--access-password-file", "/run/secrets/access_password"]
