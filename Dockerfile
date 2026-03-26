FROM python:3.11-slim

WORKDIR /app

# System deps for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Install circuitforge-core from sibling directory (compose sets context: ..)
COPY circuitforge-core/ ./circuitforge-core/
RUN pip install --no-cache-dir -e ./circuitforge-core

# Install snipe
COPY snipe/ ./snipe/
WORKDIR /app/snipe
RUN pip install --no-cache-dir -e .

# Install Playwright + Chromium (after snipe deps so layer is cached separately)
RUN pip install --no-cache-dir playwright playwright-stealth && \
    playwright install chromium && \
    playwright install-deps chromium

EXPOSE 8510
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8510"]
