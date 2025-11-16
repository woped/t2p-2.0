# Use an official Python runtime as a base image
FROM python:3.13-alpine

ENV FLASK_APP=flasky.py \
    FLASK_CONFIG=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN addgroup -S flasky && adduser -S -G flasky flasky

WORKDIR /home/flasky

# Requirements kopieren + installieren (als root)
COPY --chown=flasky:flasky requirements requirements
RUN python -m venv venv && venv/bin/pip install -r requirements/docker.txt

# App-Dateien kopieren (mit Ownership direkt setzen)
COPY --chown=flasky:flasky app app
COPY --chown=flasky:flasky flasky.py config.py boot.sh ./

# Rechte setzen (noch root, oder direkt per COPY + Ausführbit gesetzt)
RUN chmod 0750 boot.sh
USER flasky

# run-time configuration
EXPOSE 5000
ENTRYPOINT ["./boot.sh"]