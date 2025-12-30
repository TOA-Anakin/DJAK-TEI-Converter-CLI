#!/bin/bash

# Usage: ./odt2xml.sh [environment]
# environment: local | testing | production (default: local)

# Set default environment to 'local' if not specified
ENVIRONMENT=${1:-local}

DOCKER_COMPOSE_FILE=".docker/$ENVIRONMENT/docker-compose.yml"

if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    echo "Error: Docker-compose file for '$ENVIRONMENT' environment not found."
    exit 1
fi

echo "Starting ODT extraction in '$ENVIRONMENT' environment..."

# We run a bash command inside the container to handle the wildcard globbing (*) correctly
docker compose -f "$DOCKER_COMPOSE_FILE" run --rm converter bash -c '
    cd input

    # Delete existing XML files first
    echo "Removing old XML files..."
    rm -f *.xml

    count=0
    for f in *.odt; do
        # Check if file exists to avoid error if no ODTs are found
        [ -e "$f" ] || continue
        
        echo "Processing: $f"
        # Extract content.xml to stdout and redirect to a .xml file of the same name
        unzip -p "$f" content.xml > "${f%.odt}.xml"
        count=$((count+1))
    done
    
    if [ $count -eq 0 ]; then
        echo "No .odt files found in /input directory."
    else
        echo "Successfully extracted files: $count"
    fi
'