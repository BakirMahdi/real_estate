FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user: this container does scraping, LLM calls, and ML
# training (real attack surface), and it bind-mounts host directories
# (./logs, ./models, ./data) that a compromised root process could write to
# freely. uid/gid 1000 matches the default first user on most Linux hosts; if
# those bind-mounted host directories are owned by a different uid there,
# `chown -R 1000:1000 logs models data` on the host fixes write permission.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "scraper.main:app", "--host", "0.0.0.0", "--port", "8000"]