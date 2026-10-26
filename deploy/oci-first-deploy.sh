#!/usr/bin/env bash
# First deploy of the standalone NEXORA Gateway beside the monorepo gateway, on the OCI host (nexora-platform).
# Run ON the server, e.g. from your Mac:
#   ssh -i <your OCI key> opc@92.5.69.99 'bash -s' < deploy/oci-first-deploy.sh
# Safe to rerun: deploy/.env.prod is created once and never overwritten; secrets are never printed.
set -euo pipefail
OWNER="${USER:-opc}"

echo "== preflight"; df -h / | tail -1; free -h | sed -n 2p
[ "$(df --output=pcent / | tail -1 | tr -dc 0-9)" -lt 85 ] || { echo "disk over 85%: run 'sudo docker builder prune -af' first"; exit 1; }
sudo docker network ls --format '{{.Name}}' | grep -qx nexora_default || { echo "nexora_default network missing, stopping"; exit 1; }

echo "== code"
sudo mkdir -p /opt/gateway && sudo chown "$OWNER": /opt/gateway
[ -d /opt/gateway/.git ] || git clone https://github.com/xsmartbartx/Secure_AI_API_Gateway.git /opt/gateway
git -C /opt/gateway pull --ff-only
git -C /opt/gateway log --oneline -1

echo "== env (created once, never overwritten)"
cd /opt/gateway/deploy
if [ ! -f .env.prod ]; then
  (umask 077; cat > .env.prod <<EOF
GATEWAY_WEB_HOST=gateway-next.onenexora.com
GATEWAY_API_HOST=gateway-next-api.onenexora.com
POSTGRES_PASSWORD=$(openssl rand -hex 24)
CREDENTIAL_ENCRYPTION_KEY=$(openssl rand -base64 32)
AUTH_JWKS_URL=https://clerk.onenexora.com/.well-known/jwks.json
AUTH_ISSUER=https://clerk.onenexora.com
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_Y2xlcmsub25lbmV4b3JhLmNvbSQ=
EOF
  )
  echo "created deploy/.env.prod (mode 600)"
else
  echo "deploy/.env.prod already exists, kept"
fi

echo "== build and start the gateway stack"
sudo docker compose --env-file .env.prod -f compose.prod.yml up -d --build
sudo docker compose --env-file .env.prod -f compose.prod.yml ps --format '{{.Service}} {{.Status}}'

echo "== edge (recreates Caddy once so it joins gateway_default; a few seconds of blip on every site)"
cd /opt/nexora && git pull --ff-only
sudo docker compose -f infrastructure/edge/docker-compose.yml up -d

echo "== checks (certificates can take up to a minute)"
for i in 1 2 3 4 5 6; do
  api=$(curl -s -o /dev/null -w '%{http_code}' https://gateway-next-api.onenexora.com/v1/health || true)
  web=$(curl -s -o /dev/null -w '%{http_code}' https://gateway-next.onenexora.com/ || true)
  echo "api=$api web=$web"; [ "$api" = 200 ] && [ "$web" = 200 ] && break; sleep 10
done
curl -s -o /dev/null -w 'old gateway.onenexora.com: %{http_code}\n' https://gateway.onenexora.com/ || true
echo "NOW back up CREDENTIAL_ENCRYPTION_KEY from /opt/gateway/deploy/.env.prod into a password manager."
