FROM python:3.14-alpine

WORKDIR /app

RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    linux-headers \
    python3-dev \
    libffi-dev \
    openblas-dev \
    gfortran

# Create virtual environment
RUN python -m venv /opt/venv

# Activate virtual environment
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Shared directory for the SQLite DB — mounted as a named volume
# so web, celery, and celery-beat all use the same db.sqlite3 file.
RUN mkdir -p /data

# Expose Django port
EXPOSE 8000