FROM python:3.12-slim

WORKDIR /app

COPY packages/engine-py /app/packages/engine-py
COPY packages/cli /app/packages/cli
COPY packs /app/packs
COPY policy.yaml /app/policy.yaml
COPY rules.yaml /app/rules.yaml
COPY lexshield.yaml /app/lexshield.yaml

RUN pip install --no-cache-dir -e /app/packages/engine-py -e /app/packages/cli

EXPOSE 8787

CMD [
  "lexshield",
  "run",
  "--host",
  "0.0.0.0",
  "--port",
  "8787",
  "--config",
  "/app/lexshield.yaml",
  "--i-understand-bind-all"
]
