FROM python:3.11-slim

# Install core system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    libnss3 \
    libnspr4 \
    libasound2 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Force Playwright to use this folder for browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/app/pw-browsers

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# INSTALL CHROMIUM AND THE HEADLESS SHELL
RUN playwright install chromium --with-deps

COPY . .

ENV PORT=10000
CMD ["python", "main.py"]
