#!/bin/sh
cd "$(dirname "$0")" || exit 1

if [ -f /tmp/filewheel.pid ] && kill -0 "$(cat /tmp/filewheel.pid)" 2>/dev/null; then
    echo "already running, pid $(cat /tmp/filewheel.pid)"
    exit 0
fi

while true; do
    python3 main.py >>/tmp/filewheel.log 2>&1 &
    echo $! >/tmp/filewheel.pid
    wait "$(cat /tmp/filewheel.pid)"
    echo "$(date '+%Y-%m-%d %H:%M:%S') filewheel exited, restarting" >>/tmp/filewheel.log
    sleep 2
done
