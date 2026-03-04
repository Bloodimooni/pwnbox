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

# --- Reversing and Privesc — Joshua ---
# Compile admin tool
RUN mkdir -p /opt/corpchat && \
    sed 's|"./data/|"/data/|g' reversing-challenge/admin-tools.c | \
    gcc -x c - -o /opt/corpchat/corpchat-admin -lsqlite3 -O0 -no-pie && \
    chmod 755 /opt/corpchat/corpchat-admin

RUN mkdir -p /data/uploads /data/uploads/tools /data/backups /data/logs /app/scripts

# Create low-privilege service account that the Flask app runs as.
# /app is root-owned but group-readable by corpchat (app code is read-only at runtime).
# /data is fully owned by corpchat so the app can write the DB, logs, and uploads.
# /data/uploads and /data/uploads/tools are 777 so any user (incl. CTF reverse-shell)
# can write there — intentional: enables the wildcard-tar privilege escalation challenge.
RUN useradd -r -s /bin/false -M corpchat && \
    chown -R root:corpchat /app && \
    chmod -R g+rX,o-rwx /app && \
    chown -R corpchat:corpchat /data && \
    chmod 755 /data && \
    chmod 777 /data/uploads /data/uploads/tools

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
