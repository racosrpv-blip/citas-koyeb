FROM python:3.10-bullseye

ENV DEBIAN_FRONTEND=noninteractive

# Instalar Chromium + ChromeDriver del sistema (siempre compatibles entre sí)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "main.py"]
