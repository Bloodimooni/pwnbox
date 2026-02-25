FROM python:3.11-slim

ARG INSTALL_NETBIRD=false

WORKDIR /app

# Install build dependencies and system tools
RUN apt-get update && \
    apt-get install -y gcc libsqlite3-dev sudo curl iproute2 && \
    rm -rf /var/lib/apt/lists/*

# Conditionally install NetBird (only needed for CTF infra deployments)
RUN if [ "$INSTALL_NETBIRD" = "true" ]; then \
        curl -fsSL https://pkgs.netbird.io/install.sh | sh; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Compile admin tool: fix paths for container, then build
RUN mkdir -p /opt/corpchat && \
    sed 's|"./data/|"/data/|g' admin-tools.c | \
    gcc -x c - -o /opt/corpchat/corpchat-admin -lsqlite3 -O0 -no-pie && \
    chmod 755 /opt/corpchat/corpchat-admin

RUN mkdir -p /data/uploads /data/backups /data/logs

EXPOSE 5000

ENV FLASK_CONFIG=config.ProductionConfig
ENV SECRET_KEY=corpchat-default-secret
ENV DATABASE_DIR=/data
ENV UPLOAD_FOLDER=/data/uploads
ENV LOG_DIR=/data/logs

CMD ["/bin/bash", "/app/start.sh"]
