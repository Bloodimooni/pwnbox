FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/uploads /data/backups /data/logs

EXPOSE 5000

ENV FLASK_CONFIG=config.ProductionConfig
ENV SECRET_KEY=corpchat-default-secret
ENV DATABASE_DIR=/data
ENV UPLOAD_FOLDER=/data/uploads
ENV LOG_DIR=/data/logs

CMD ["python", "app.py"]
