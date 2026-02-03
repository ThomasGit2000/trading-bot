FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

CMD ["python", "-m", "src.bot"]
