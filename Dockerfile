FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

ARG UID=1000
RUN useradd --uid ${UID} --no-create-home --home-dir /app app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY squarex ./squarex

USER app
ENV PYTHONUNBUFFERED=1
