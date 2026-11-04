#!/bin/sh
# Free-plan option: run the Celery worker, with its beat, inside the API container, next to uvicorn.
#
# start.sh launches this script in the background only when EMBEDDED_WORKER=1, so nothing changes until it is switched on.
# It never takes the API down: a missing broker or a crashing worker is written to the log and the API keeps serving.
#
#   EMBEDDED_WORKER=1            switch it on (anything else: not started)
#   CELERY_BROKER_URL            required, the Redis / Key Value *internal* URL; CELERY_RESULT_BACKEND takes the same one
#   EMBEDDED_WORKER_QUEUES       queues to consume, default "sends,automation,webhooks" (the Blueprint's worker)
#   EMBEDDED_WORKER_LOGLEVEL     default "info"
#
# Sending is unchanged: every send still goes through send_gate / dispatch (kill switch, pause, limits, sandbox).
# The broker URL carries a password on a paid Key Value, so it is never printed here: only the variable names are.
set -u

say() { echo "[embedded-worker] $*" >&2; }

queues="${EMBEDDED_WORKER_QUEUES:-sends,automation,webhooks}"

case "${CELERY_BROKER_URL:-}" in
  "")
    say "EMBEDDED_WORKER=1 but CELERY_BROKER_URL is empty: no worker started. Set CELERY_BROKER_URL and CELERY_RESULT_BACKEND to the Key Value internal URL."
    exit 0
    ;;
  redis://localhost* | redis://127.* | rediss://localhost* | rediss://127.*)
    say "CELERY_BROKER_URL points at this container itself, where no Redis runs: no worker started. Use the Key Value internal URL."
    exit 0
    ;;
  redis://* | rediss://*) ;;
  *)
    say "CELERY_BROKER_URL is not a redis:// URL: no worker started."
    exit 0
    ;;
esac

case "$queues" in
  "" | *[!a-z,]*)
    say "EMBEDDED_WORKER_QUEUES must be a comma-separated list of lowercase queue names (sends,automation,webhooks): no worker started."
    exit 0
    ;;
esac

say "starting the worker with its beat (queues: $queues, one process, no fork)"

# One worker process and no child pool (--pool=solo) keeps memory low on the 512 MB free instance; the beat runs beside it
# (--beat), so the scheduled tasks of celery_app.py need no second service. A tight crash loop backs off up to two minutes.
delay=5
while :; do
  began=$(date +%s)
  celery -A celery_app worker --beat --pool=solo --without-gossip --without-mingle \
    --schedule /tmp/celerybeat-schedule --queues "$queues" --loglevel "${EMBEDDED_WORKER_LOGLEVEL:-info}"
  status=$?
  ran=$(($(date +%s) - began))
  if [ "$ran" -ge 60 ]; then delay=5; fi
  say "celery exited (status $status) after ${ran}s; restarting in ${delay}s"
  sleep "$delay"
  delay=$((delay * 2))
  if [ "$delay" -gt 120 ]; then delay=120; fi
done
