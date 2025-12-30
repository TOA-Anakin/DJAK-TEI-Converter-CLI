#!/bin/bash

if [ "$#" -ne 2 ]; then
    echo "Usage: ./env.sh [environment] [action]"
    echo "       environment: local | testing | production"
    echo "       action: up | start | down | stop"
    exit 1
fi

ENVIRONMENT=$1
ACTION=$2

DOCKER_COMPOSE_FILE=".docker/$ENVIRONMENT/docker-compose.yml"

if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
    echo "Error: Docker-compose file for '$ENVIRONMENT' environment not found."
    exit 1
fi

case $ACTION in
    up)
        echo "Starting the containers for the $ENVIRONMENT environment..."
        if [[ "$ENVIRONMENT" == "production" ]]; then
            docker compose -f $DOCKER_COMPOSE_FILE build --no-cache
            docker compose -f $DOCKER_COMPOSE_FILE up -d --force-recreate
        elif [[ "$ENVIRONMENT" == "testing" ]]; then
            docker compose -f $DOCKER_COMPOSE_FILE up -d --build
        else
            # docker compose -f $DOCKER_COMPOSE_FILE up --build
            docker compose -f $DOCKER_COMPOSE_FILE build --no-cache
            docker compose -f $DOCKER_COMPOSE_FILE up -d --force-recreate
        fi
        ;;
    start)
        echo "Starting the containers for the $ENVIRONMENT environment..."
        docker compose -f $DOCKER_COMPOSE_FILE start
        ;;
    down)
        echo "Removing the containers for the $ENVIRONMENT environment..."
        docker compose -f $DOCKER_COMPOSE_FILE down
        ;;
    stop)
        echo "Stopping the containers for the $ENVIRONMENT environment..."
        docker compose -f $DOCKER_COMPOSE_FILE stop
        ;;
    *)
        echo "Invalid action: $ACTION"
        echo "Valid actions are: up | down"
        exit 1
        ;;
esac