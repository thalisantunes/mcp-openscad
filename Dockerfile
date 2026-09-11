# Reproducible build for MCP directory indexers (Glama) and for running the
# server in a container. The server speaks stdio, so run it with -i.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends openscad \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

ENTRYPOINT ["mcp-openscad"]
