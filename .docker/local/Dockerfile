# Official Python 3.6 image
FROM python:3.6.15-slim-bullseye

# Set a working directory inside the container
WORKDIR /app

# Install system dependencies (needed by the 'lxml' Python library and others)
RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt1-dev \
    xsltproc \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install Python packages
COPY ./scripts/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy necessary files into the container
COPY /scripts /app/scripts/