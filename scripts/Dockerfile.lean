FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates git python3-pip sudo && \
    rm -rf /var/lib/apt/lists/*

# Install Lean via elan
RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.elan/bin:${PATH}"
RUN lean --version

RUN pip3 install --break-system-packages fastapi uvicorn pydantic

WORKDIR /workspace
COPY lean_service.py /workspace/lean_service.py

EXPOSE 9407
CMD ["uvicorn", "lean_service:app", "--host", "0.0.0.0", "--port", "9407"]
