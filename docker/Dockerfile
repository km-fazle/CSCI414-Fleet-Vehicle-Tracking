FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/work/api:/work/simulator:/work/data \
    PATH=/opt/fleettrace-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        ca-certificates \
        curl \
        gnupg \
        iproute2 \
        nftables \
        tcpdump \
        iperf3 \
        iputils-ping \
        traceroute \
        openssl \
        procps \
        && rm -rf /var/lib/apt/lists/*

# MongoDB Community 8.0 for Ubuntu 24.04 (noble), amd64 and arm64.
RUN curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc \
        | gpg --dearmor -o /usr/share/keyrings/mongodb-server-8.0.gpg \
    && echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" \
        > /etc/apt/sources.list.d/mongodb-org-8.0.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mongodb-org-server mongodb-mongosh \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt /tmp/api-requirements.txt
COPY api/requirements-dev.txt /tmp/api-requirements-dev.txt
COPY simulator/requirements.txt /tmp/simulator-requirements.txt

RUN python3 -m venv /opt/fleettrace-venv \
    && /opt/fleettrace-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/fleettrace-venv/bin/pip install --no-cache-dir \
        -r /tmp/api-requirements.txt \
        -r /tmp/api-requirements-dev.txt \
        -r /tmp/simulator-requirements.txt

WORKDIR /work
CMD ["sleep", "infinity"]
