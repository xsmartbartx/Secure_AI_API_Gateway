#!/usr/bin/env bash
# Step 2 of the first deploy: bring the shared Caddy up to date with NEXORA main (adds the gateway-next routes) and join it
# to gateway_default. Run ON the server:
#   ssh -i <your OCI key> opc@92.5.69.99 'bash -s' < deploy/oci-edge-step.sh
# The server's Caddyfile had an uncommitted edit that main already contains (cspm -> cspm-web-1:80, PR #80). A copy of it is
# saved to ~/Caddyfile.local-<date>.diff before it is replaced by the committed version.
set -euo pipefail
cd /opt/nexora

echo "== preflight: both external networks must exist, or compose would fail"
for n in gateway_default cspm_internal nexora_default vigilo-self-host_default neurawall_default omniflow_default; do
  sudo docker network ls --format '{{.Name}}' | grep -qx "$n" && echo "ok  $n" || { echo "MISSING network $n, stopping (nothing changed)"; exit 1; }
done

echo "== only the Caddyfile may differ from the commit"
dirty=$(git status --porcelain --untracked-files=no | grep -v 'infrastructure/edge/Caddyfile$' || true)
[ -z "$dirty" ] || { echo "other tracked files modified, stopping:"; echo "$dirty"; exit 1; }

if ! git diff --quiet -- infrastructure/edge/Caddyfile; then
  out="$HOME/Caddyfile.local-$(date -u +%Y%m%d%H%M).diff"
  git diff -- infrastructure/edge/Caddyfile > "$out"
  echo "saved local edit to $out"
  git checkout -- infrastructure/edge/Caddyfile
fi
git pull --ff-only
git log --oneline -1

echo "== validate the new Caddyfile before touching the running proxy"
sudo docker run --rm -v "$PWD/infrastructure/edge":/etc/caddy:ro caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 \
  && echo "Caddyfile valid" || { echo "Caddyfile INVALID, stopping (proxy untouched)"; exit 1; }

echo "== recreate Caddy so it joins gateway_default (a few seconds of blip on every site)"
sudo docker compose -f infrastructure/edge/docker-compose.yml up -d

echo "== checks (certificates can take up to a minute)"
for i in 1 2 3 4 5 6; do
  api=$(curl -s -o /dev/null -w '%{http_code}' https://gateway-next-api.onenexora.com/v1/health || true)
  web=$(curl -s -o /dev/null -w '%{http_code}' https://gateway-next.onenexora.com/ || true)
  echo "api=$api web=$web"; [ "$api" = 200 ] && [ "$web" = 200 ] && break; sleep 10
done
for h in onenexora.com gateway.onenexora.com cspm.onenexora.com vigilo.onenexora.com; do
  curl -s -o /dev/null -w "$h: %{http_code}\n" "https://$h/" || true
done
echo "NOW back up CREDENTIAL_ENCRYPTION_KEY from /opt/gateway/deploy/.env.prod into a password manager."
