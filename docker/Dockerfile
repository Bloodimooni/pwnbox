FROM python:3.11-slim

ARG INSTALL_NETBIRD=false

WORKDIR /app

# Install build dependencies and system tools
RUN apt-get update && \
    apt-get install -y gcc libsqlite3-dev sudo curl iproute2 openssh-server cron && \
    rm -rf /var/lib/apt/lists/*

# Conditionally install NetBird
RUN if [ "$INSTALL_NETBIRD" = "true" ]; then \
        curl -fsSL https://pkgs.netbird.io/install.sh | sh; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Compile admin tool
RUN mkdir -p /opt/corpchat && \
    sed 's|"./data/|"/data/|g' reversing-challenge/admin-tools.c | \
    gcc -x c - -o /opt/corpchat/corpchat-admin -lsqlite3 -O0 -no-pie && \
    chmod 755 /opt/corpchat/corpchat-admin

RUN mkdir -p /data/uploads /data/backups /data/logs

# SSH: replace default config with a clean authoritative one so Debian defaults
# can't silently override PasswordAuthentication
RUN mkdir -p /var/run/sshd && \
    printf 'Port 22\nPasswordAuthentication yes\nPermitRootLogin no\nUsePAM yes\nLogLevel VERBOSE\nAcceptEnv LANG LC_*\nSubsystem sftp /usr/lib/openssh/sftp-server\n' \
        > /etc/ssh/sshd_config

EXPOSE 8080 22

ENV FLASK_CONFIG=config.ProductionConfig
ENV SECRET_KEY=corpchat-default-secret
ENV DATABASE_DIR=/data
ENV UPLOAD_FOLDER=/data/uploads
ENV LOG_DIR=/data/logs

CMD ["python", "/app/entrypoint.py"]
