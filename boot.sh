#!/bin/sh
. venv/bin/activate

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_URL="${REDIS_URL:-redis://${REDIS_HOST}:${REDIS_PORT}/0}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"

redis-server /home/flasky/redis.conf &
REDIS_PID=$!

cleanup() {
	if [ -n "${GUNICORN_PID:-}" ] && kill -0 "$GUNICORN_PID" 2>/dev/null; then
		kill "$GUNICORN_PID" 2>/dev/null || true
	fi
	if kill -0 "$REDIS_PID" 2>/dev/null; then
		kill "$REDIS_PID" 2>/dev/null || true
	fi
}

trap cleanup INT TERM

i=0
until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; do
	i=$((i + 1))
	if [ "$i" -ge 30 ]; then
		echo "Redis did not become ready in time" >&2
		cleanup
		exit 1
	fi
	sleep 1
done

gunicorn \
	-b :5000 \
	--workers "$GUNICORN_WORKERS" \
	--threads "$GUNICORN_THREADS" \
	--timeout "$GUNICORN_TIMEOUT" \
	--access-logfile - \
	--error-logfile - \
	flasky:app &
GUNICORN_PID=$!

wait "$GUNICORN_PID"
STATUS=$?
cleanup
wait "$REDIS_PID" 2>/dev/null || true
exit "$STATUS"
