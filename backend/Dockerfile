FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including imapsync and Perl modules
RUN apt-get update && apt-get install -y \
    perl \
    libio-socket-ssl-perl \
    libmail-imapclient-perl \
    libjson-webtoken-perl \
    libmodule-scandeps-perl \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install imapsync from CPAN or source
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    && curl -L https://imapsync.lamiral.info/imapsync -o /usr/local/bin/imapsync \
    && chmod +x /usr/local/bin/imapsync \
    || echo "Warning: imapsync installation from URL failed, will try CPAN" \
    && apt-get remove -y build-essential libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
