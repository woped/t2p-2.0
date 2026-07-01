#!/bin/sh
# POSIX `.` (not the bash-only `source`) since the shebang is /bin/sh.
. venv/bin/activate

# Gunicorn: threads give I/O-bound concurrency (the orchestrator spends its time
# waiting on the connector/transformer), and the timeout must outlast the sync
# fallback's full generation. The async path keeps each call short, so this is a
# safety ceiling. All three are env-overridable. No Redis here: t2p-2.0 only
# polls the connector's async endpoints; it owns no job state of its own.
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-8}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-300}"

exec gunicorn \
	-b :5000 \
	--workers "$GUNICORN_WORKERS" \
	--threads "$GUNICORN_THREADS" \
	--timeout "$GUNICORN_TIMEOUT" \
	--access-logfile - \
	--error-logfile - \
	flasky:app
