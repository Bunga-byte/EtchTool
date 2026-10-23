FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.lock.txt ./requirements.lock.txt
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then \
      cat /etc/ssl/certs/ca-certificates.crt /run/secrets/build_ca > /tmp/frip-build-ca.pem; \
      export PIP_CERT=/tmp/frip-build-ca.pem; \
    fi; \
    pip install --no-cache-dir --require-hashes -r requirements.lock.txt \
    && rm -f /tmp/frip-build-ca.pem \
    && useradd --create-home --uid 10001 frip
COPY --chown=frip:frip backend/ /app/backend/
COPY --chown=frip:frip fixtures/ /app/fixtures/
COPY --chown=frip:frip integration_manifests/ /app/integration_manifests/
COPY --chown=frip:frip schemas/ /app/schemas/
RUN chown -R frip:frip /app
USER frip
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && if [ \"${FRIP_MODE:-synthetic}\" = synthetic ]; then python -m app.seed; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
