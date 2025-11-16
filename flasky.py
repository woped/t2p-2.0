from app import create_app, REQUEST_COUNT, REQUEST_LATENCY, API_CALL_DURATION
import click
import pytest
import logging

logger = logging.getLogger(__name__)

# Use the application-level Prometheus metrics defined in app.__init__ to avoid
# registering the same metric names multiple times (which causes CollectorRegistry errors).
app = create_app()
logger.debug("Flask app created in flasky.py", extra={"app_name": app.name})


@app.cli.command("test")
@click.option('--cov', is_flag=True, help="Zeige Testabdeckung (Coverage).")
def test_command(cov):
    """Führe alle Tests im Ordner 'tests/' aus."""
    logger.info("Running test suite via CLI", extra={"coverage": bool(cov)})
    args = ["tests"]
    if cov:
        args += ["--cov=app", "--cov-report=term-missing"]
    result = pytest.main(args)
    logger.info("Test suite finished", extra={"exit_code": result})
    raise SystemExit(result)

