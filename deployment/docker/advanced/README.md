# Advanced Docker Configuration

This folder contains auxiliary assets for advanced Docker deployments.

## Files

- `Dockerfile_dgx`: GPU-oriented build with micromamba, CUDA PyTorch, vLLM, and the advanced requirements set
- `requirements_fix.txt`: dependency set used by `Dockerfile_dgx`
- `nginx.conf`: reverse-proxy configuration for locked-down access patterns
- `docker_compose_reverse.yml`: legacy/alternate reverse-proxy compose variant kept for reference
- `create_variables.sh`: helper script that generates a local `.env` with UID/GID/PWD
- `recreate_and_start.sh`: convenience wrapper around the main reverse compose file

## When To Use This Folder

Use these files only for specialized deployments where the baseline compose files are insufficient, typically when:

- GPU-specific image tuning is required
- a reverse proxy is part of the deployment topology
- UID/GID alignment with the host matters

## Notes

- The canonical reverse-proxy entrypoint is now:
  - `deployment/docker/compose/docker-compose_reverse.yml`
- The `docker_compose_reverse.yml` file in this folder is kept as a documented alternate variant, not the primary entrypoint.
