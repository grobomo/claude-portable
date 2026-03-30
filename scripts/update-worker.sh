#!/bin/bash
set -euo pipefail
#
# update-worker.sh -- Self-update a worker container from ECR golden image.
#
# Pulls the latest image, stops the current container, restarts with the same
# volumes and environment, then re-registers with the dispatcher.
#
# Environment:
#   AWS_REGION          AWS region for ECR login (default: us-east-2)
#   DISPATCHER_URL      Dispatcher base URL (e.g. http://10.0.1.5:8080)
#   CONTAINER_NAME      Name of the running worker container (default: auto-detect)
#   WORKER_ID           Instance identifier (default: from container env or hostname)
#

ECR_REPO="752266476357.dkr.ecr.us-east-2.amazonaws.com/hackathon26/worker"
AWS_REGION="${AWS_REGION:-us-east-2}"
CONTAINER_NAME="${CONTAINER_NAME:-}"

log() { echo "[update-worker] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
die() { log "FATAL: $*"; exit 1; }

# ---------- Find the running worker container ----------
if [ -z "$CONTAINER_NAME" ]; then
  CONTAINER_NAME=$(docker ps --filter "ancestor=${ECR_REPO}" --format '{{.Names}}' | head -1)
  [ -z "$CONTAINER_NAME" ] && die "No running container found for image ${ECR_REPO}. Set CONTAINER_NAME."
  log "Auto-detected container: ${CONTAINER_NAME}"
fi

# Verify container is running
docker inspect "$CONTAINER_NAME" >/dev/null 2>&1 || die "Container '${CONTAINER_NAME}' not found."

# ---------- Step 1: ECR login ----------
log "Logging in to ECR (${AWS_REGION})..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "752266476357.dkr.ecr.${AWS_REGION}.amazonaws.com" \
  || die "ECR login failed."

# ---------- Step 2: Pull latest image ----------
log "Pulling latest image..."
OLD_IMAGE_ID=$(docker inspect --format '{{.Image}}' "$CONTAINER_NAME")
docker pull "${ECR_REPO}:latest" || die "Image pull failed."
NEW_IMAGE_ID=$(docker inspect --format '{{.Id}}' "${ECR_REPO}:latest")

if [ "$OLD_IMAGE_ID" = "$NEW_IMAGE_ID" ]; then
  log "Already running latest image. Nothing to do."
  exit 0
fi
log "New image detected: ${NEW_IMAGE_ID:0:20}..."

# ---------- Step 3: Capture current container config ----------
log "Capturing container config from ${CONTAINER_NAME}..."

# Extract environment variables (as -e flags)
ENV_ARGS=()
while IFS= read -r envvar; do
  [ -z "$envvar" ] && continue
  ENV_ARGS+=("-e" "$envvar")
done < <(docker inspect --format '{{range .Config.Env}}{{.}}{{"\n"}}{{end}}' "$CONTAINER_NAME")

# Extract volume mounts (as -v flags)
VOLUME_ARGS=()
while IFS= read -r mount; do
  [ -z "$mount" ] && continue
  VOLUME_ARGS+=("-v" "$mount")
done < <(docker inspect --format '{{range .Mounts}}{{.Source}}:{{.Destination}}{{if .Mode}}:{{.Mode}}{{end}}{{"\n"}}{{end}}' "$CONTAINER_NAME")

# Extract port mappings (as -p flags)
PORT_ARGS=()
while IFS= read -r portmap; do
  [ -z "$portmap" ] && continue
  PORT_ARGS+=("-p" "$portmap")
done < <(docker inspect --format '{{range $p, $conf := .NetworkSettings.Ports}}{{range $conf}}{{.HostPort}}:{{$p}}{{"\n"}}{{end}}{{end}}' "$CONTAINER_NAME" 2>/dev/null)

# Extract restart policy
RESTART_POLICY=$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CONTAINER_NAME")
RESTART_ARGS=()
if [ -n "$RESTART_POLICY" ] && [ "$RESTART_POLICY" != "no" ]; then
  RESTART_ARGS=("--restart" "$RESTART_POLICY")
fi

# Extract network mode
NETWORK=$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$CONTAINER_NAME")
NETWORK_ARGS=()
if [ -n "$NETWORK" ] && [ "$NETWORK" != "default" ] && [ "$NETWORK" != "bridge" ]; then
  NETWORK_ARGS=("--network" "$NETWORK")
fi

# ---------- Step 4: Stop and remove old container ----------
log "Stopping container ${CONTAINER_NAME}..."
docker stop "$CONTAINER_NAME" --time 30 || log "WARNING: stop timed out, forcing..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

# ---------- Step 5: Start new container ----------
log "Starting new container..."
docker run -d \
  --name "$CONTAINER_NAME" \
  "${ENV_ARGS[@]}" \
  "${VOLUME_ARGS[@]}" \
  "${PORT_ARGS[@]}" \
  "${RESTART_ARGS[@]}" \
  "${NETWORK_ARGS[@]}" \
  "${ECR_REPO}:latest"

log "Container ${CONTAINER_NAME} started with new image."

# ---------- Step 6: Re-register with dispatcher ----------
DISPATCHER_URL="${DISPATCHER_URL:-}"
if [ -n "$DISPATCHER_URL" ]; then
  # Pull worker identity from the new container or fall back to env/hostname
  WORKER_ID="${WORKER_ID:-}"
  if [ -z "$WORKER_ID" ]; then
    WORKER_ID=$(docker exec "$CONTAINER_NAME" printenv WORKER_ID 2>/dev/null \
      || docker exec "$CONTAINER_NAME" printenv CLAUDE_PORTABLE_ID 2>/dev/null \
      || hostname)
  fi

  LOCAL_IP=$(curl -s -m 2 http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null \
    || hostname -I 2>/dev/null | awk '{print $1}' \
    || echo "unknown")

  REGISTER_JSON="{\"worker_id\":\"${WORKER_ID}\",\"ip\":\"${LOCAL_IP}\",\"role\":\"worker\",\"capabilities\":[\"continuous-claude\",\"tdd-pipeline\"],\"event\":\"update\",\"image\":\"${NEW_IMAGE_ID:0:20}\"}"

  log "Registering with dispatcher at ${DISPATCHER_URL}..."
  if curl -s -f -X POST \
      -H "Content-Type: application/json" \
      -d "$REGISTER_JSON" \
      --connect-timeout 5 --max-time 10 \
      "${DISPATCHER_URL}/worker/register" >/dev/null 2>&1; then
    log "Registered with dispatcher."
  else
    log "WARNING: Could not register with dispatcher (will retry on next heartbeat)."
  fi
else
  log "DISPATCHER_URL not set, skipping registration."
fi

log "Update complete."
