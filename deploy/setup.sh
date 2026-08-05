#!/usr/bin/env bash
# Geometry Agent — automated deployment for Ubuntu 22.04
# Usage: sudo bash setup.sh [PORT]
#   PORT defaults to 80, falls back to 8080 if 80 is blocked.

set -euo pipefail

APP_DIR="/opt/geometry-agent"
PORT="${1:-80}"

echo "=== Geometry Agent Deployment ==="
echo "App dir:  $APP_DIR"
echo "Port:     $PORT"

# ---- System dependencies ----
echo ">>> Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    texlive-xetex texlive-lang-chinese \
    nginx git curl > /dev/null 2>&1
echo "    System packages done."

# ---- Python venv ----
if [ ! -d "$APP_DIR/.venv" ]; then
    echo ">>> Creating Python virtual environment..."
    python3 -m venv "$APP_DIR/.venv"
fi
echo ">>> Installing Python dependencies..."
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -e "$APP_DIR[dev]" -q 2>&1 | tail -1
"$APP_DIR/.venv/bin/pip" install gunicorn -q 2>&1 | tail -1
echo "    Python deps done."

# ---- .env file ----
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo ">>> Created .env from template — EDIT IT with your API key!"
    fi
fi

# ---- Outputs directory ----
mkdir -p "$APP_DIR/outputs"
chown -R ubuntu:ubuntu "$APP_DIR" 2>/dev/null || true

# ---- systemd service ----
echo ">>> Installing systemd service..."
cp "$APP_DIR/deploy/geometry-agent.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable geometry-agent

# ---- nginx ----
echo ">>> Configuring nginx on port $PORT..."
sed "s/__PORT__/$PORT/g" "$APP_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/geometry-agent
ln -sf /etc/nginx/sites-available/geometry-agent /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

if nginx -t 2>/dev/null; then
    systemctl reload nginx 2>/dev/null || systemctl start nginx
    echo "    nginx OK on port $PORT"
else
    echo "    nginx config test failed, trying fallback..."
    if [ "$PORT" = "80" ]; then
        echo "    Port 80 blocked? Trying 8080..."
        sed "s/__PORT__/8080/g" "$APP_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/geometry-agent
        if nginx -t 2>/dev/null; then
            systemctl reload nginx
            PORT=8080
            echo "    nginx OK on port 8080"
        else
            echo "    ERROR: nginx config invalid"
            nginx -t 2>&1
            exit 1
        fi
    else
        nginx -t 2>&1
        exit 1
    fi
fi

# ---- Start app ----
echo ">>> Starting geometry-agent..."
systemctl restart geometry-agent
sleep 2

# ---- Verify ----
echo ""
echo "=== Health check ==="
if curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
    echo "  API:       OK"
else
    echo "  API:       FAIL (check: journalctl -u geometry-agent -n 20)"
fi

PUBLIC_IP=$(curl -sf ifconfig.me 2>/dev/null || curl -sf icanhazip.com 2>/dev/null || echo "UNKNOWN")
echo ""
echo "=== Deployment complete ==="
echo "  Web UI:     http://${PUBLIC_IP}:${PORT}"
echo "  API docs:   http://${PUBLIC_IP}:${PORT}/docs"
echo "  Health:     http://${PUBLIC_IP}:${PORT}/api/health"
echo ""
echo "  Manage:     systemctl [start|stop|restart|status] geometry-agent"
echo "  Logs:       journalctl -u geometry-agent -f"
echo "  Nginx logs: tail -f /var/log/nginx/access.log"
echo ""
if [ ! -s "$APP_DIR/.env" ] || grep -q 'your_api_key_here' "$APP_DIR/.env" 2>/dev/null; then
    echo "  ⚠️  EDIT $APP_DIR/.env with LLM_API_KEY, then:"
    echo "     sudo systemctl restart geometry-agent"
fi