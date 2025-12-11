# Use the official Selenium standalone Chrome image to avoid runtime chrome/chromedriver issues
FROM selenium/standalone-chrome:115.0

USER root
WORKDIR /app

# Install Python & pip (image includes some libs but may not include pip)
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps
COPY requirements.txt /app/
RUN python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Copy app sources
COPY . /app

EXPOSE 5000

# Run gunicorn with single worker and single thread to reduce memory pressure
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "1", "--timeout", "120"]
