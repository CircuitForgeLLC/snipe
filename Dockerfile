FROM python:3.11-slim

WORKDIR /app

# Install circuitforge-core from sibling directory (compose sets context: ..)
COPY circuitforge-core/ ./circuitforge-core/
RUN pip install --no-cache-dir -e ./circuitforge-core

# Install snipe
COPY snipe/ ./snipe/
WORKDIR /app/snipe
RUN pip install --no-cache-dir -e .

EXPOSE 8506
CMD ["streamlit", "run", "app/app.py", "--server.port=8506", "--server.address=0.0.0.0"]
