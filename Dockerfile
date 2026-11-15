FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
COPY static ./static
ENV PYTHONUNBUFFERED=1
CMD ["python", "server.py"]
