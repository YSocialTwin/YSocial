# Docker Compose Layout

This directory contains all Docker Compose variants for the project.

## Structure

- `compose/`: primary compose entrypoints
- `advanced/`: optional supporting files and specialized GPU/reverse-proxy assets

## Compose Files

- `compose/docker-compose.yml`: standard SQLite-backed deployment
- `compose/docker-compose_gpu.yml`: SQLite-backed deployment with NVIDIA runtime enabled
- `compose/docker-compose-postgresql.yml`: PostgreSQL-backed deployment
- `compose/docker-compose-postgresql_gpu.yml`: PostgreSQL-backed deployment with NVIDIA runtime enabled
- `compose/docker-compose_reverse.yml`: reverse-proxy + Ollama/GPU deployment using the advanced DGX-oriented image

## Usage

Run all commands from the repository root.

### Standard

```bash
docker compose -f deployment/docker/compose/docker-compose.yml up --build
```

### Standard + GPU

```bash
docker compose -f deployment/docker/compose/docker-compose.yml -f deployment/docker/compose/docker-compose_gpu.yml up --build
```

### PostgreSQL

```bash
docker compose -f deployment/docker/compose/docker-compose-postgresql.yml up --build
```

### PostgreSQL + GPU

```bash
docker compose -f deployment/docker/compose/docker-compose-postgresql.yml -f deployment/docker/compose/docker-compose-postgresql_gpu.yml up --build
```

### Reverse Proxy + Ollama

```bash
docker compose -f deployment/docker/compose/docker-compose_reverse.yml up --build
```

## Supporting Files

- `deployment/nginx/nginx.conf`: default Nginx configuration used by the standard compose files
- `deployment/docker/advanced/nginx.conf`: specialized reverse-proxy example for constrained deployments

## Differences

- SQLite vs PostgreSQL: controlled by the base compose file selected
- CPU vs GPU: controlled by the GPU overlay variants
- Reverse proxy deployment: includes Nginx, Ollama, GPU runtime settings, and the advanced image build

See `advanced/README.md` for the supporting files used by the specialized reverse-proxy/GPU setup.
