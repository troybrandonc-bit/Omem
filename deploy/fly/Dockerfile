# Minimal Fly.io image: the pip package serves API + dashboard on one port.
FROM python:3.12-slim
RUN pip install --no-cache-dir omem-infrastructure
ENV OMEM_HOST=0.0.0.0 OMEM_AUTH=password OMEM_ALLOW_INSECURE_BIND=1 OMEM_DATA_DIR=/data
CMD ["omem-server", "8080"]
