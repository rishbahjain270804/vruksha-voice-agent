#!/usr/bin/env bash
# One-shot setup for a fresh Ubuntu VM (Oracle Always Free) — installs the app as a 24/7
# service behind Caddy with automatic HTTPS (needed for the browser mic).
#
# Run it like this (fill in your own values first):
#   export DOMAIN=yourname.duckdns.org
#   export GROQ_API_KEY=gsk_...
#   export ELEVENLABS_API_KEY=sk_...
#   export PROOF_TOKEN=proof_mcp_...
#   curl -fsSL https://raw.githubusercontent.com/rishbahjain270804/vruksha-voice-agent/master/deploy/oracle-setup.sh | sudo -E bash
set -euo pipefail

: "${DOMAIN:?set DOMAIN (e.g. yourname.duckdns.org)}"
: "${GROQ_API_KEY:?set GROQ_API_KEY}"
: "${ELEVENLABS_API_KEY:?set ELEVENLABS_API_KEY}"
: "${PROOF_TOKEN:?set PROOF_TOKEN}"

REPO=https://github.com/rishbahjain270804/vruksha-voice-agent.git
APP=/opt/vruksha

echo "== packages =="
apt-get update -y
apt-get install -y python3-venv python3-pip git curl debian-keyring debian-archive-keyring apt-transport-https

echo "== Caddy (reverse proxy + auto HTTPS) =="
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

echo "== app =="
rm -rf "$APP" && git clone --depth 1 "$REPO" "$APP"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install --upgrade pip
"$APP/.venv/bin/pip" install fastapi "uvicorn[standard]" python-multipart pydantic python-dotenv httpx groq "psycopg[binary]" pyotp

echo "== env =="
cat > "$APP/.env" <<ENV
PROOF_DRY_RUN=1
PROOF_TOKEN=${PROOF_TOKEN}
PROOF_BASE=https://proof.zeromaintenanceengineer.in
STT_PROVIDER=groq
GROQ_API_KEY=${GROQ_API_KEY}
GROQ_MODEL=openai/gpt-oss-120b
LLM_PROVIDER=groq
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL
ELEVENLABS_MODEL=eleven_multilingual_v2
DEFAULT_LANG=en
ENV
chmod 600 "$APP/.env"

echo "== systemd service =="
cat > /etc/systemd/system/vruksha.service <<UNIT
[Unit]
Description=Vruksha voice agent
After=network.target
[Service]
WorkingDirectory=${APP}
EnvironmentFile=${APP}/.env
Environment=PYTHONUTF8=1
ExecStart=${APP}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now vruksha

echo "== Caddy site (HTTPS via Let's Encrypt) =="
cat > /etc/caddy/Caddyfile <<CADDY
${DOMAIN} {
    reverse_proxy 127.0.0.1:8000
}
CADDY
systemctl restart caddy

echo "== firewall (Oracle Ubuntu images block ports by default) =="
iptables -I INPUT -p tcp --dport 80 -j ACCEPT || true
iptables -I INPUT -p tcp --dport 443 -j ACCEPT || true
netfilter-persistent save 2>/dev/null || (apt-get install -y iptables-persistent && netfilter-persistent save) || true

echo ""
echo "DONE. Give Caddy ~30s to get the certificate, then open:  https://${DOMAIN}"
echo "Logs:   journalctl -u vruksha -f   |   journalctl -u caddy -f"
