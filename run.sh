#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ -f /tmp/filewheel.pid ] && kill -0 "$(cat /tmp/filewheel.pid)" 2>/dev/null; then
    echo "already running, pid $(cat /tmp/filewheel.pid)"
    exit 0
fi
nohup python3 main.py >/tmp/filewheel.log 2>&1 &
echo $! >/tmp/filewheel.pid
sleep 1
if kill -0 "$(cat /tmp/filewheel.pid)" 2>/dev/null; then
    echo "started, pid $(cat /tmp/filewheel.pid)"
else
    echo "failed to start, see /tmp/filewheel.log"
    tail -20 /tmp/filewheel.log
fi
