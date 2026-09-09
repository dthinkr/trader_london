#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/root/trading_platform}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.server.yml}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

cd "$APP_DIR"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Missing $COMPOSE_FILE in $APP_DIR"
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "Missing .env in $APP_DIR"
  exit 1
fi

if [ ! -f "back/config/auth/firebase-service-account.json" ]; then
  echo "Missing back/config/auth/firebase-service-account.json"
  exit 1
fi

if ! grep -q '^NGROK_AUTHTOKEN=' .env && [ -z "${NGROK_AUTHTOKEN:-}" ]; then
  echo "Missing NGROK_AUTHTOKEN in .env or environment"
  exit 1
fi

if ! grep -q '^ADMIN_PASSWORD=' .env && [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "Missing ADMIN_PASSWORD in .env or environment"
  exit 1
fi

echo "Updating repository from origin/${DEPLOY_BRANCH}..."
git fetch origin "$DEPLOY_BRANCH"
git reset --hard "origin/${DEPLOY_BRANCH}"

# Pull the backend image directly rather than via `docker compose pull`.
#
# On the deployment host `docker` is the podman compatibility shim, but
# `docker compose` hands off to a separate, real Compose binary. The two do not
# share a credential store: a `docker login` is recorded where podman keeps its
# credentials, while the external Compose binary looks for a Docker-style
# config.json and finds nothing. A registry that needs authentication therefore
# fails under `compose pull` even directly after a successful login.
#
# `docker pull` stays inside the shim, so it uses the credentials the login
# actually wrote. Compose then finds the image already present locally and does
# not need to pull it itself.
BACK_IMAGE="$(awk '/^[[:space:]]*back:/{f=1} f && /^[[:space:]]*image:/{print $2; exit}' "$COMPOSE_FILE")"
if [ -z "$BACK_IMAGE" ]; then
  echo "ERROR: could not determine the backend image from $COMPOSE_FILE" >&2
  exit 1
fi

echo "Pulling backend image ($BACK_IMAGE)..."
# Do NOT swallow this failure. Continuing with a stale local image makes a broken
# deploy look successful: the service stays up, the run reports success, and the
# new code is silently never deployed. Fail loudly instead.
if ! docker pull "$BACK_IMAGE"; then
  echo "ERROR: could not pull the backend image from the registry." >&2
  echo "Refusing to continue, because doing so would silently redeploy the previous version." >&2
  exit 1
fi

echo "Stopping existing compose services..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans || true

echo "Removing stale trading_platform containers..."
OLD_NGROK_CONTAINERS="$(docker ps -a --format '{{.ID}} {{.Names}}' | awk '/ngrok/ {print $1}')"
if [ -n "$OLD_NGROK_CONTAINERS" ]; then
  docker rm -f $OLD_NGROK_CONTAINERS || true
fi

OLD_PLATFORM_CONTAINERS="$(docker ps -a --format '{{.ID}} {{.Names}}' | awk '/trading_platform/ {print $1}')"
if [ -n "$OLD_PLATFORM_CONTAINERS" ]; then
  docker rm -f $OLD_PLATFORM_CONTAINERS || true
fi

echo "Freeing containers that still publish port 8000..."
PORT_8000_CONTAINERS="$(docker ps --format '{{.ID}} {{.Ports}}' | awk '/127\.0\.0\.1:8000|0\.0\.0\.0:8000|:8000->/ {print $1}')"
if [ -n "$PORT_8000_CONTAINERS" ]; then
  docker rm -f $PORT_8000_CONTAINERS || true
fi

echo "Starting services..."
docker compose -f "$COMPOSE_FILE" up -d --build --remove-orphans

docker compose -f "$COMPOSE_FILE" ps
