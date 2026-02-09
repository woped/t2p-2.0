# t2p-2.0

## Description

This repository contains a Flask-based web API for converting and transforming process models.

## Features

- "/test_connection" Route - Connection test/health endpoint
- "/generate_bpmn" and "/generate_BPMN" Routes - Generate BPMN output
- "/generate_pnml" and "/generate_PNML" Routes - Generate PNML output
- "/metrics" Route - Prometheus metrics endpoint
- "/api/swagger.yaml" Route - Swagger/OpenAPI specification
- "/api_call" Route - Deprecated endpoint for backward compatibility

## Installation

Install WSL as instructed here:
https://learn.microsoft.com/en-us/windows/wsl/install - The recommended Distro is Ubuntu 22.04

Install Docker as instructed here:
https://docs.docker.com/desktop/wsl/

### Prerequisites

### Setting Up Your Local Environment

After cloning this repository, it's essential to [set up git hooks](https://github.com/woped/woped-git-hooks/blob/main/README.md#activating-git-hooks-after-cloning-a-repository) to ensure project standards.

To set up the local environment without docker, use these commands:

- Create local environment:
  From project root folder use:
  ```bash
  python -m venv venv
  source venv/bin/activate
  ```
- Install the requirements:
  ```bash
  pip install -r requirements/dev.txt
  ```

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
http://localhost:4000/test_connection
```

### Test if the endpoint is working using curl

Open a terminal and send a GET request to the following URL:

```bash
curl http://localhost:4000/test_connection
```

## Versioning

The service version is stored in the root-level `version.py` file under the `__version__` attribute. This value is used for container tagging in CI.

## Running unit tests

First install the requirements, see section "Setting Up Your Local Environment" for more information.

### In the app folder, run the following commands:

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
