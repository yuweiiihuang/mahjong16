FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM python:3.13-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.13-slim-bookworm AS standard
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /app/.venv /app/.venv
COPY app/ app/
COPY domain/ domain/
COPY bots/ bots/
COPY ui/ ui/
COPY configs/ configs/
RUN mkdir -p /var/lib/mahjong16 && chown 10001:10001 /var/lib/mahjong16 && chmod 700 /var/lib/mahjong16
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app.web", "--host", "0.0.0.0", "--port", "8000", "--access-password-file", "/run/secrets/access_password", "--record-db", "/var/lib/mahjong16/hands.sqlite3"]

# Build native artifacts on the target Linux architecture; standard builds stay opt-in.
FROM python:3.13-slim-bookworm AS native-build
RUN apt-get update && apt-get install -y --no-install-recommends git patch g++ ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY scripts/build_meowcats.py scripts/build_meowcats.py
COPY bots/native/meowcats bots/native/meowcats
RUN git clone https://github.com/fight5566jay/MeowCaTS_1.0.git upstream \
    && git -C upstream checkout --detach 1e6ae5320d5e0d3d3b5d017ff83e05d02b9ba162 \
    && python scripts/build_meowcats.py upstream native \
    && tar -czf native/source.tar.gz scripts bots native/vendor native/bridge.cpp native/build-command.json

FROM standard AS advanced
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
COPY --from=native-build /build/native/bridge /opt/meowcats/bridge
COPY --from=native-build /build/native/runtime /opt/meowcats/runtime
COPY --from=native-build /build/native/source.tar.gz /opt/meowcats/source.tar.gz
COPY bots/native/meowcats/LICENSE /opt/meowcats/LICENSE
COPY --chmod=755 deploy/meowcats/entrypoint.sh /opt/meowcats/entrypoint.sh
ENTRYPOINT ["/opt/meowcats/entrypoint.sh"]

FROM standard AS runtime
