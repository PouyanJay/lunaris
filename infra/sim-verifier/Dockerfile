# Isolated execution appliance: no application code, credentials, mounts, or network at runtime.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble@sha256:aa81288e738725378becba5b3e06cb0f3a7f012a610e87e8d767a090ea3f740d
RUN pip install --no-cache-dir playwright==1.62.0 \
    && pip uninstall -y virtualenv pip \
    && rm -rf /root/.cache
COPY infra/sim-verifier/runner.py /opt/verifier/runner.py
USER 1000:1000
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "/opt/verifier/runner.py"]
