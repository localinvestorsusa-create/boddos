# BODDOS node container. Point it at a config via a mounted volume + env.
#   docker build -t boddos .
#   docker run --rm -p 8787:8787 \
#     -v $PWD/config:/config \
#     -e BODDOS_MESH_PSK=... -e BODDOS_VAULT_PASSPHRASE=... \
#     boddos --config /config/boddos.yaml
#
# Note: host Ollama is reached via models.ollama_url. On Docker Desktop use
# http://host.docker.internal:11434; on Linux use the host IP or --network host.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY boddos ./boddos
RUN pip install --no-cache-dir .

EXPOSE 8787
ENTRYPOINT ["python", "-m", "boddos"]
CMD ["--config", "/config/boddos.yaml"]
