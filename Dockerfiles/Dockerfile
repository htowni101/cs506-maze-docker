FROM python:3.11-slim
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main_cli.py"]
