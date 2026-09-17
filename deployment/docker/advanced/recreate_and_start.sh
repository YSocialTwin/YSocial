#/bin/bash

 docker compose -f deployment/docker/compose/docker-compose_reverse.yml build
 docker compose -f deployment/docker/compose/docker-compose_reverse.yml up -d
 # docker compose -f deployment/docker/compose/docker-compose_reverse.yml down