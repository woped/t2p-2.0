# Use a base image with JDK
FROM openjdk:17-jdk-alpine

# Set the working directory inside the container
WORKDIR /app

# Copy the jar file into the Docker image
COPY target/t2p-validation-0.0.1-SNAPSHOT.jar /app/

# Copy the resources into the Docker image
COPY src/main/resources/ /app/src/main/resources/

# Expose the port your Spring Boot app runs on
EXPOSE 8080

# Command to run the application
ENTRYPOINT ["java", "-jar", "t2p-validation-0.0.1-SNAPSHOT.jar"]