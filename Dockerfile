# Use the official lightweight Python image.
FROM python:3.11-slim

# Allow statements and log messages to be sent straight to the logs
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Cloud Run expects the service to listen on $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

# Start the server via gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]
