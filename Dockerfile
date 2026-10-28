# Lightspeed Tracker
# SPDX-License-Identifier: GPL-3.0-or-later
FROM python:3.13-slim

LABEL org.opencontainers.image.title="Lightspeed Tracker" \
      org.opencontainers.image.source="https://github.com/molinarif02/lightspeed-tracker" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

ARG OOKLA_VERSION=1.2.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tzdata \
 && case "$(uname -m)" in \
      aarch64) A=aarch64 ;; x86_64) A=x86_64 ;; armv7l) A=armhf ;; \
      *) echo "unsupported arch $(uname -m)"; exit 1 ;; \
    esac \
 && curl -fsSL "https://install.speedtest.net/app/cli/ookla-speedtest-${OOKLA_VERSION}-linux-${A}.tgz" \
    | tar -xz -C /usr/local/bin speedtest \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && useradd -u 1000 -m -d /data app

ENV HOME=/data PYTHONUNBUFFERED=1 PORT=60884
WORKDIR /app
COPY app.py index.html ./
USER app
EXPOSE 60884
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','60884'))"
CMD ["python", "app.py"]
