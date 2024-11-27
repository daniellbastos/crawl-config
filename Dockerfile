FROM python:3.12-slim-bullseye

RUN mkdir /app

ENV PYTHONUNBUFFERED 1
ENV APP_FOLDER=/app

# Install dependencies (??? maybe we can remove xauth and xvfv ???)
RUN apt update -y \
    && apt upgrade -y \
    && apt install -y ffmpeg xauth xvfb git openssl \
    && apt clean

WORKDIR ${APP_FOLDER}

RUN pip install --upgrade pip pip-tools==7.3.0

COPY requirements.in /app/requirements.in

# Install web dependencies
RUN echo "---------- installing web dependencies --------------" \
    && pip-compile /app/requirements.in -o /app/requirements.txt \
    && pip install -r /app/requirements.txt

RUN echo "---------- installing crawler dependencies --------------"
RUN playwright install chromium
RUN playwright install-deps


RUN echo "---------- cleaning apt data --------------" \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

ENV PYTHONPATH=/app

COPY . ${APP_FOLDER}

# CMD ["bin/app.sh", "web"]
