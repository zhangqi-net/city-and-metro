#!/usr/bin/env bash
# City & Metro 本地服务控制脚本
# 用法: ./serve.sh <start|stop|restart|status|open|log>
# 环境变量: CM_PORT（默认 8123）, CM_HOST（默认 127.0.0.1，设 0.0.0.0 可让局域网/手机访问）

set -u
PORT="${CM_PORT:-8123}"
HOST="${CM_HOST:-127.0.0.1}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="citymetro-${PORT}"
LOG="/tmp/${TAG}.log"
PIDF="/tmp/${TAG}.pid"
PYF="/tmp/${TAG}.py"

gen_py() {
  cat > "$PYF" <<PY
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
os.chdir("$ROOT")
class H(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = ThreadingHTTPServer(("$HOST", $PORT), H)
try:
    srv.serve_forever()
except KeyboardInterrupt:
    pass
PY
}

running_pid() {
  local p=""
  [ -f "$PIDF" ] && p="$(cat "$PIDF" 2>/dev/null)"
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo "$p"; return; fi
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1
}

url() { echo "http://127.0.0.1:${PORT}"; }

case "${1:-start}" in
  start)
    p="$(running_pid)"
    if [ -n "$p" ]; then
      echo "已在运行 PID $p → $(url)"
      exit 0
    fi
    gen_py
    nohup python3 "$PYF" > "$LOG" 2>&1 &
    echo $! > "$PIDF"
    for i in $(seq 1 40); do
      c="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' --max-time 2 "$(url)/index.html" 2>/dev/null)"
      [ "$c" = "200" ] && break
      sleep 0.25
    done
    p="$(running_pid)"
    if [ -z "$p" ]; then echo "启动失败，查看日志: $LOG"; tail -5 "$LOG" 2>/dev/null; exit 1; fi
    code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' --max-time 5 "$(url)/index.html")"
    echo "已启动 PID $p  $HOST:$PORT  (HTTP $code)"
    echo "访问: $(url)"
    ;;
  stop)
    p="$(running_pid)"
    if [ -z "$p" ]; then echo "未在运行"; rm -f "$PIDF"; exit 0; fi
    kill "$p" 2>/dev/null; sleep 0.5
    kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null
    rm -f "$PIDF"
    echo "已停止 PID $p"
    ;;
  restart) "$0" stop; sleep 0.5; "$0" start ;;
  status)
    p="$(running_pid)"
    if [ -z "$p" ]; then echo "未运行 (端口 $PORT)"; exit 1; fi
    code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' --max-time 5 "$(url)/index.html")"
    echo "运行中 PID $p  $(url)  HTTP ${code:-无响应}"
    echo "日志 $LOG"
    ;;
  open)
    p="$(running_pid)"
    [ -z "$p" ] && "$0" start >/dev/null
    open "$(url)"
    echo "已打开 $(url)"
    ;;
  log) tail -n "${2:-40}" -f "$LOG" 2>/dev/null || echo "无日志: $LOG" ;;
  *)
    echo "用法: $0 <start|stop|restart|status|open|log>"; exit 1 ;;
esac
