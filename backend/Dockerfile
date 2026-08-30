FROM python:3.11-slim

WORKDIR /app

# System packages: Java is required for the PySpark driver JVM.
# gcc is required to compile some Python C extensions (psycopg2-binary, bcrypt).
# Note: Spark itself is NOT downloaded here — `pyspark==3.5.0` in requirements.txt
# already bundles the full Spark distribution (~270 MB of JARs). The separate
# `wget` download that used to live here was redundant and added ~600 MB.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    default-jre-headless \
    procps \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# After `pip install pyspark`, Spark lives inside the package itself.
# SPARK_HOME must point there so findspark / SparkContext can locate JARs.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Set SPARK_HOME to the pyspark package directory (contains bin/, jars/, python/).
RUN python -c \
    "import pyspark, os; path=os.path.dirname(pyspark.__file__); \
    open('/etc/spark_home', 'w').write(path)"
ENV SPARK_HOME=/usr/local/lib/python3.11/site-packages/pyspark
ENV PATH="${SPARK_HOME}/bin:${PATH}"
ENV PYTHONPATH="${SPARK_HOME}/python:${SPARK_HOME}/python/lib/py4j-0.10.9.7-src.zip:${PYTHONPATH}"
ENV PYSPARK_PYTHON=/usr/local/bin/python3
ENV PYSPARK_DRIVER_PYTHON=/usr/local/bin/python3

# Copy application
COPY . .

# Create logs directory
RUN mkdir -p logs

# Run as a non-root user. UID/GID 1000 matches the default first non-root
# user on most Linux hosts, which keeps bind-mount permissions sane in
# docker-compose dev usage. chown covers /app (app code + logs/) and the
# Spark home marker file written above.
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser \
    && chown -R appuser:appuser /app /etc/spark_home
USER appuser

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
