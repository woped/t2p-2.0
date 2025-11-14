# Use an official Python runtime as a base image
FROM python:3.13-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy the backend directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable if needed
ENV NAME World

ENV FLASK_APP=app.backend.app:create_app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
ENV PYTHONPATH=/app/app/backend
CMD ["flask", "run"]
