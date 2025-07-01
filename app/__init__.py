import sys
import os
import click
import pytest

# Add backend directory to Python path
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Import create_app function
from app.backend.app import create_app

# Create Flask app instance for CLI
app = create_app()

# Test CLI Commands
@app.cli.command("test")
@click.option('--cov', is_flag=True, help="Show test coverage.")
@click.option('--integration', is_flag=True, help="Run integration tests as well (requires API + keys).")
def test_command(cov, integration):
    """Run all tests in 'tests/' directory."""
    args = ["tests"]
    if not integration:
        # Exclude integration tests by default
        args += ["-m", "not integration"]
    # If integration=True, run all tests (no marker filtering)
    if cov:
        args += ["--cov=app", "--cov-report=term-missing"]
    raise SystemExit(pytest.main(args))

@app.cli.command("test-integration")
@click.option('--cov', is_flag=True, help="Show test coverage.")
def test_integration_command(cov):
    """Run only integration tests (requires API + API keys)."""
    args = ["tests", "-m", "integration", "-v"]
    if cov:
        args += ["--cov=app", "--cov-report=term-missing"]
    raise SystemExit(pytest.main(args))

if __name__ == "__main__":
    app.run(debug=True)
