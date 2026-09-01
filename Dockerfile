FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 reaper
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY playbooks ./playbooks
RUN pip install --upgrade pip && pip install .

USER reaper
EXPOSE 8787
ENTRYPOINT ["reaper"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8787"]

