FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN useradd -m appuser && mkdir -p /data && chown -R appuser:appuser /app /data
USER appuser

ENV DB_PATH=/data/data.db
ENV PORT=8000
ENV SESSION_TTL_HOURS=12
ENV COOKIE_SECURE=true

EXPOSE 8000
VOLUME ["/data"]

CMD ["python", "app.py"]
