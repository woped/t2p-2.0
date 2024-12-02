# t2p-2.0

## Description

This repository is for the source code handling the web-api call of llm providers as GPT from Open AI.

## Features

- "/test" Route - Route used for connection testing
- "/api_call" Route - Route used for processing the textual information from the request. The route takes 2 arguments inside the POST request: "text": "The process description in string format" and "api_key": "OPENAI (not AzureOpenAI!) key". #ADD THE RETURN FORMAT ACCORDING TO THE PARSER
- Feature 3
- Add more features as needed

## Installation

Install WSL as instructed here:
https://learn.microsoft.com/en-us/windows/wsl/install - The recommended Distro is Ubuntu 22.04

Install Docker as instructed here:
https://docs.docker.com/desktop/wsl/

### Prerequisites

### Setting Up Your Local Environment

To set up the local envoronment without docker, use these commands:

- Create local environment:
  From project root folder use:
  ```bash
  python -m venv venv
  source venv/bin/activate
  ```
- Navigate into the app/backend folder:
  ```bash
  cd app/backend
  ```
- Install the requirements:
  ```bash
  pip install -r requirements.txt
  ```

#### Running the Project as docker image

To run the project as docker image, navigate to the backend directory and run the following commands:

Build the container (usually needed only once):

```bash
docker build -t my_flask_app .
```

Run the app:

```bash
docker run -p 4000:5000 my_flask_app
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

## Running unit tests

First install the requirements, see section "Setting Up Your Local Environment" for more information.

### In the app folder, run the following commands:

To run all the tests, use the following command:

```bash
coverage run -m unittest discover unittest
```

To see the coverage report, use the following command:

```bash
coverage report -m
```

If you want to see the coverage report in html format, use the following command:

```bash
coverage html
```

Then navigate to the htmlcov directory and open the index.html file in a browser.
