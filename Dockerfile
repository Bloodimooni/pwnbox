FROM python:3.11-slim

WORKDIR /app

# Install build dependencies and system tools
RUN apt-get update && \
    apt-get install -y gcc libsqlite3-dev sudo && \
    rm -rf /var/lib/apt/lists/*

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

CMD ["python", "entrypoint.py"]
