FROM python:3.12-slim
WORKDIR /srv
# hash-pinned, wheels only: nothing from the network runs build scripts
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.lock
# only what the service needs (no tests, no local databases or env files)
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
RUN useradd --system --uid 10001 --no-create-home app && chown -R app /srv
USER app
ENV ENV=prod PYTHONUNBUFFERED=1
EXPOSE 8000
# migrations run as a release step: `alembic upgrade head`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
