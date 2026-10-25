#!/bin/sh
cd "$(dirname "$0")" || exit 1

# Stop any already-running Daisy (a previous clone/version) so the
# freshly cloned code is what actually launches, instead of the old
# instance silently staying alive and this script just no-op'ing.
pkill -f 'supervise[.]sh' 2>/dev/null
if [ -f /tmp/filewheel.pid ]; then
    kill "$(cat /tmp/filewheel.pid)" 2>/dev/null
    rm -f /tmp/filewheel.pid
fi
pkill -f 'python3 main[.]py' 2>/dev/null
sleep 1

VER=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "daisy $VER starting" > /tmp/filewheel.log
nohup python3 main.py >> /tmp/filewheel.log 2>&1 &
echo $! > /tmp/filewheel.pid
sleep 1
if kill -0 "$(cat /tmp/filewheel.pid)" 2>/dev/null; then
    echo "started daisy $VER, pid $(cat /tmp/filewheel.pid)"
else
    echo "failed to start, see /tmp/filewheel.log"
    tail -20 /tmp/filewheel.log
fi
