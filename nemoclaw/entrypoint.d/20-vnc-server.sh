#!/usr/bin/env bash
# Start a lightweight VNC desktop for GUI tools inside the sandbox.
# Connect from the host with: vncviewer localhost:5900

set -euo pipefail

VNC_DISPLAY="${VNC_DISPLAY:-0}"
DISPLAY=":${VNC_DISPLAY}"
VNC_PORT="$((5900 + VNC_DISPLAY))"
VNC_GEOMETRY="${VNC_GEOMETRY:-1280x1024}"
VNC_DEPTH="${VNC_DEPTH:-24}"
VNC_PASSWORD="${VNC_PASSWORD:-nemo1234}"
VNC_HOME="/sandbox/.vnc"
LOG_FILE="${VNC_HOME}/vnc-server.log"

mkdir -p "$VNC_HOME"

if [[ "${VNC_DISABLED:-false}" == "true" ]]; then
  echo "VNC server disabled (VNC_DISABLED=true)" | tee -a "$LOG_FILE"
  exit 0
fi

export USER="${USER:-sandbox}"
export HOME="/sandbox"
export DISPLAY

if [[ ! -f "$VNC_HOME/passwd" ]]; then
  echo "$VNC_PASSWORD" | vncpasswd -f > "$VNC_HOME/passwd"
  chmod 600 "$VNC_HOME/passwd"
fi

cat > "$VNC_HOME/xstartup" <<'EOF'
#!/usr/bin/env bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
xsetroot -solid '#222222'
if command -v fluxbox >/dev/null 2>&1; then
  exec fluxbox
fi
xterm -geometry 100x30+20+20 &
wait
EOF
chmod +x "$VNC_HOME/xstartup"

vncserver -kill "$DISPLAY" >/dev/null 2>&1 || true

echo "[$(date)] Starting VNC on ${DISPLAY} (${VNC_GEOMETRY}x${VNC_DEPTH}), TCP port ${VNC_PORT}" | tee -a "$LOG_FILE"
nohup vncserver "$DISPLAY" \
  -geometry "$VNC_GEOMETRY" \
  -depth "$VNC_DEPTH" \
  -rfbauth "$VNC_HOME/passwd" \
  -localhost no \
  >> "$LOG_FILE" 2>&1 &

echo "VNC server starting (display=${DISPLAY}, port=${VNC_PORT}, log=${LOG_FILE})" | tee -a "$LOG_FILE"
echo "Connect from host: vncviewer localhost:${VNC_PORT}" | tee -a "$LOG_FILE"
