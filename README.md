# t2p-2.0

## Description

This repository contains a Flask-based web API for converting and transforming process models.

## Features

- "/v2/health" Route - Current connection test/health endpoint
- "/v2/generate/bpmn" and "/v2/generate/pnml" Routes - Current versioned generation API
- "/v2/models" Route - Lists the available provider/model pairs (proxied from the connector)
- "/test_connection", "/generate_bpmn", "/generate_BPMN", "/generate_pnml" and "/generate_PNML" Routes - Functional deprecated compatibility endpoints until 2026-12-01
- "/_/_/echo" Route - Operational liveness endpoint
- "/example" Route - Trivial static stub used as a routing smoke test
- "/metrics" Route - Prometheus metrics endpoint
- "/swagger" Route - Interactive Swagger UI rendered from the OpenAPI spec
- "/api/swagger.yaml" Route - Swagger/OpenAPI specification
- "/api_call" Route - Removed endpoint after its 2025-12-31 sunset date

## Installation

Install WSL as instructed here:
https://learn.microsoft.com/en-us/windows/wsl/install - The recommended Distro is Ubuntu 22.04

Install Docker as instructed here:
https://docs.docker.com/desktop/wsl/

### Setting Up Your Local Environment

After cloning this repository, it's essential to [set up git hooks](https://github.com/woped/woped-git-hooks/blob/main/README.md#activating-git-hooks-after-cloning-a-repository) to ensure project standards.

To set up the local environment without docker, use these commands:

- Create and activate the local environment:
  From project root folder use:
  ```bash
  # Windows
  python -m venv .venv
  .\.venv\Scripts\activate
  
  # Mac/Linux
  python -m venv .venv
  source .venv/bin/activate
  ```
- Install the requirements:
  ```bash
  pip install -r requirements/dev.txt
  ```
- Run the Flask app locally:
  ```bash
  flask --app flasky run
  ```
  (`.flaskenv` already sets `FLASK_APP=flasky.py`, so a bare `flask run` works
  too.)

#### Running the Project as docker image

To run the project as docker image, use the project root directory (where the Dockerfile is located) and run the following commands:

Build the container (usually needed only once):

```bash
docker build -t t2p-api .
```

Run the app:

```bash
docker run -p 4000:5000 t2p-api
```

## Local testing if the endpoint is working

Before you start testing the endpoint, make sure the app is running. If you are not sure how to run the app, please refer to the previous section

### Test if the endpoint is working using Postman

Open Postman and send a GET request to the following URL:

```bash
http://localhost:4000/v2/health
```

### Test if the endpoint is working using curl

Open a terminal and send a GET request to the following URL:

```bash
curl http://localhost:4000/v2/health
```

## Versioning

The service version is stored in the root-level `version.py` file under the `__version__` attribute. This value is used for container tagging in CI.

## Running unit tests

First install the requirements, see section "Setting Up Your Local Environment" for more information.

### From the project root, run the following commands:

To run all the tests, use the following command:

```bash
pytest -v
```

To see the coverage report, use the following command:

```bash
pytest --cov=app --cov-report=term-missing -v
```

If you want to see the coverage report in html format, use the following command:

```bash
coverage html
```

Then navigate to the htmlcov directory and open the index.html file in a browser.
