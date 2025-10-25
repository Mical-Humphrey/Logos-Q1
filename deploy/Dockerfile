FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    LOGOS_ENV=paper

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints.txt requirements/ /tmp/requirements/
RUN pip install --upgrade pip \
    && pip install --requirement /tmp/requirements/requirements.txt

COPY . /app

# Ensure helper scripts are executable when baked into the image.
RUN chmod +x scripts/ops/*.sh

CMD ["python", "-m", "logos.run", "--mode", "paper"]
