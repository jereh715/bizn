# Use the official Microsoft Playwright image
# This image ALREADY has Python, Chromium, and all dependencies installed
FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# We NO LONGER need "playwright install" because it's already in the image!
# We just need to tell Playwright where it is
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

ENV PORT=10000
CMD ["python", "main.py"]
