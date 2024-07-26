# Set the base image to Python 3.12 and create a new stage
FROM python:3.12 as requirements-stage

# Set the working directory
WORKDIR /tmp

# Install Poetry
RUN pip install poetry

# Copy pyproject.toml and poetry.lock* files
COPY ./pyproject.toml ./poetry.lock* /tmp/

# Install dependencies using poetry and export them to requirements.txt
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

# Set the base image to Python 3.12
FROM python:3.12

# Links Docker image with repository
LABEL org.opencontainers.image.source https://github.com/joaovitoriasilva/endurain

# Set the working directory
WORKDIR /app

# Copy requirements.txt from requirements-stage to /app
COPY --from=requirements-stage /tmp/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy the directory app contents to /app
COPY app /app

# Make port 80 available to the world outside this container
EXPOSE 80

# Define environment variables
ENV DB_HOST="mariadb"
ENV DB_PORT=3306
ENV DB_USER="endurain"
ENV DB_PASSWORD="changeme"
ENV DB_DATABASE="endurain"
ENV SECRET_KEY="changeme"
ENV ALGORITHM="HS256"
ENV ACCESS_TOKEN_EXPIRE_MINUTES=30
ENV REFRESH_TOKEN_EXPIRE_DAYS=7
ENV STRAVA_CLIENT_ID="changeme"
ENV STRAVA_CLIENT_SECRET="changeme"
ENV STRAVA_AUTH_CODE="changeme"
ENV JAEGER_ENABLED="false"
ENV JAEGER_HOST="jaeger"
ENV JAEGER_PROTOCOL="http"
ENV JAGGER_PORT=4317
ENV STRAVA_DAYS_ACTIVITIES_ONLINK=30
ENV FRONTEND_PROTOCOL="http"
ENV FRONTEND_HOST="frontend:8080"
ENV GEOCODES_MAPS_API="changeme"

# Run main.py when the container launches
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]