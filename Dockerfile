# Everything refresh.sh needs: Python deps + Quarto. Data, secrets and output are mounted (see
# docker-compose.yml), never baked into the image.
#
#   docker compose build
#   docker compose run --rm dashboard          # = ./refresh.sh
FROM python:3.12-slim

ARG QUARTO_VERSION=1.12.1
ARG TARGETARCH=amd64
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl rsync \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-${TARGETARCH}.tar.gz" \
    | tar xz -C /opt \
 && ln -s "/opt/quarto-${QUARTO_VERSION}/bin/quarto" /usr/local/bin/quarto

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# The container may run as the host user (compose `user:`), so the render dir must be writable
RUN mkdir -p /app/data /site && chmod -R a+rwX /app/dashboard /app/data /site

# Use the image's Python (no .venv), publish to the mounted /site, writable HOME for Quarto/Jupyter
ENV PYTHON=/usr/local/bin/python \
    QUARTO=/usr/local/bin/quarto \
    DEPLOY_DIR=/site \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["./refresh.sh"]
