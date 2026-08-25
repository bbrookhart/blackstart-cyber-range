# BLACKSTART service image.
#
# One image serves every zone; the service and its zone are selected by the
# Compose command. That keeps the five services genuinely identical in build
# provenance, so a difference in behaviour between zones can only come from
# configuration and network attachment -- which is what the architecture
# demonstration is about.
#
# Posture: non-root, no build toolchain in the runtime layer, no shell tooling
# beyond what the base image provides, and a read-only root filesystem at run
# time (see docker-compose.yml).

# ---------------------------------------------------------------------------
# Build stage: resolve and install dependencies into a self-contained venv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS build

# uv is copied from its own published image rather than curl|sh'd, so the
# provenance of the installer is a pinned image digest rather than a live URL.
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Dependency layer: cached unless the lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra services --no-install-project

# Project layer.
COPY blackstart ./blackstart
COPY services ./services
COPY configs ./configs
COPY scenarios ./scenarios
RUN uv sync --frozen --no-dev --extra services

# ---------------------------------------------------------------------------
# Runtime stage.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="BLACKSTART" \
      org.opencontainers.image.description="Consequence-driven cyber-physical resilience range" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/blackstart-research/blackstart-cyber-range"

# Fixed uid/gid so the read-only root filesystem and volume ownership are
# predictable across hosts.
RUN groupadd --gid 10001 blackstart \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin blackstart

WORKDIR /app

COPY --from=build --chown=10001:10001 /build /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001:10001

# Every service is reached only from inside its Docker network. The single
# host-published port is declared in docker-compose.yml, bound to loopback.
EXPOSE 8080 8081 8082 8083 8084

# Overridden per service in docker-compose.yml.
CMD ["python", "-m", "uvicorn", "services.enterprise.app:app", "--host", "0.0.0.0", "--port", "8080"]
