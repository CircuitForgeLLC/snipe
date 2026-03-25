FROM python:3.11-slim

WORKDIR /app

# Install circuitforge-core from sibling directory (compose sets context: ..)
COPY circuitforge-core/ ./circuitforge-core/
RUN pip install --no-cache-dir -e ./circuitforge-core

# Install snipe
COPY snipe/ ./snipe/
WORKDIR /app/snipe
RUN pip install --no-cache-dir -e .

EXPOSE 8509
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8509", "--server.address=0.0.0.0"]
