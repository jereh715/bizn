# Updated to v1.59.0 as required by the latest Playwright library
FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Match the path to the official image's internal structure
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

ENV PORT=10000

# The -u flag ensures logs are sent to Render immediately (unbuffered)
CMD ["python", "-u", "main.py"]
