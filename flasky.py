from app import create_app
from prometheus_client import Counter, Histogram
import click
import pytest

# Prometheus Metriken
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])
API_CALL_DURATION = Histogram('api_call_duration_seconds', 'API call processing duration')

app = create_app()


@app.cli.command("test")
@click.option('--cov', is_flag=True, help="Zeige Testabdeckung (Coverage).")
def test_command(cov):
    """Führe alle Tests im Ordner 'tests/' aus."""
    args = ["tests"]
    if cov:
        args += ["--cov=app", "--cov-report=term-missing"]
    raise SystemExit(pytest.main(args))

