FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production QUOTA_DB_PATH=/app/runtime/quota.sqlite3
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser app.py LICENSE pyproject.toml ./
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser data/ data/
COPY --chown=appuser:appuser docs/privacy.md docs/terms.md docs/data-processing.md docs/
COPY --chown=appuser:appuser .streamlit/ .streamlit/
RUN mkdir -p runtime && chown appuser:appuser runtime
USER appuser
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"
CMD ["python", "-m", "src.start"]
