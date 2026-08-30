# Spark Integration for Data Quality Checks

This document describes the Spark integration implementation for distributed data quality check execution in the DQ SaaS platform.

## Overview

The Spark integration enables scalable, distributed processing of data quality checks on large datasets while maintaining a SaaS architecture where:
- **SaaS platform** handles all Spark compute and processing
- **Client data** remains in client databases (on-premise or cloud)
- **Secure connectivity** from SaaS to client data sources

## Architecture

```
┌──────────────────────────────────────────────────────┐
│          SaaS Platform (Your Infrastructure)         │
│                                                       │
│  ┌───────────┐      ┌──────────────────────────┐    │
│  │  Backend  │─────▶│   Spark Cluster          │    │
│  │ (FastAPI) │      │   (Compute Engine)       │    │
│  └───────────┘      │                          │    │
│                     │  ┌────────┐  ┌─────────┐ │    │
│                     │  │ Master │  │ Workers │ │    │
│                     │  └────────┘  └─────────┘ │    │
│                     └──────────────────────────┘    │
└─────────────┼───────────────────────────────────────┘
              │
              │ Secure Connection (TLS/VPN)
              ▼
┌──────────────────────────────────────────────────────┐
│       Client Infrastructure (Data Sources)           │
│  ┌──────────┐  ┌────────┐  ┌───────────┐           │
│  │PostgreSQL│  │ MySQL  │  │ Snowflake │           │
│  └──────────┘  └────────┘  └───────────┘           │
└──────────────────────────────────────────────────────┘
```

## Components

### 1. SparkSessionManager (`app/services/execution/spark_session_manager.py`)
- **Singleton pattern** for managing shared Spark session
- Reduces overhead by reusing sessions across checks
- Supports local mode (development) and cluster mode (production)
- Cloud-aware configuration (AWS, Azure, GCP)

### 2. SparkConnector (`app/services/datasources/connectors/spark.py`)
- Implements `BaseConnector` interface using Spark
- Supports JDBC sources (PostgreSQL, MySQL, SQL Server)
- Supports cloud data warehouses (Snowflake)
- Optimized for distributed data access

### 3. SparkCheckExecutor (`app/services/execution/spark_executor.py`)
- Executes data quality checks using Spark
- Implements intelligent execution mode selection
- Handles result processing and formatting

### 4. Enhanced RuleCompiler (`app/services/rules/compiler.py`)
- Generates Spark SQL (ANSI SQL compatible)
- Method: `compile_rule_for_spark()`
- Adjusts SQL for Spark compatibility

### 5. Updated CheckNodeHandler (`app/services/flows/node_handlers/check_node.py`)
- Integrated Spark execution path
- Automatic mode selection (direct vs Spark)
- Transparent fallback handling

### 6. CredentialManager (`app/services/datasources/credential_manager.py`)
- Secure credential storage for client data sources
- Supports multiple backends:
  - Environment variables (development)
  - AWS Secrets Manager
  - Azure Key Vault
  - GCP Secret Manager

## Execution Mode Strategy

The system automatically selects the optimal execution mode based on dataset size:

| Dataset Size | Default Mode | Behavior |
|--------------|--------------|----------|
| < 50K rows | **Direct** | Uses native database connector |
| 50K - 500K rows | **Spark** (recommended) | User can override to Direct |
| > 500K rows | **Spark** (mandatory) | Forced for performance |

Configuration via environment variables:
```bash
SPARK_AUTO_THRESHOLD=50000   # Auto-enable Spark
SPARK_FORCE_THRESHOLD=500000 # Force Spark
```

Users can override via node configuration:
```json
{
  "execution_mode": "spark"  // or "direct"
}
```

## Configuration

### Environment Variables

Key configurations in `.env`:

```bash
# Deployment
DEPLOYMENT_MODE=docker-compose  # or kubernetes, aws-emr, azure-databricks, gcp-dataproc
ENABLE_CLUSTER_MODE=false       # true for production

# Spark Configuration
SPARK_MASTER_URL=local[*]       # or spark://spark-master:7077
SPARK_DRIVER_MEMORY=2g
SPARK_EXECUTOR_MEMORY=4g
SPARK_EXECUTOR_CORES=2

# Execution Thresholds
SPARK_AUTO_THRESHOLD=50000
SPARK_FORCE_THRESHOLD=500000

# Security
SSL_VERIFY_CLIENT_CERTS=true
ALLOWED_CLIENT_NETWORKS=10.0.0.0/8,172.16.0.0/12

# Multi-tenancy
MAX_CONNECTIONS_PER_TENANT=10
MAX_CONCURRENT_CHECKS_PER_TENANT=5
```

## Deployment

### Docker Compose (Development/Small SaaS)

```bash
# Start with Spark cluster
docker-compose up

# Scale workers
docker-compose up --scale spark-worker-1=4
```

### Kubernetes (Production SaaS)

```bash
# Apply configurations
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/spark-config.yaml
kubectl apply -f k8s/spark-master.yaml
kubectl apply -f k8s/spark-worker.yaml
kubectl apply -f k8s/backend.yaml

# Verify
kubectl get pods -n data-quality
kubectl get hpa -n data-quality
```

See [SPARK_INTEGRATION_PLAN.md](../../SPARK_INTEGRATION_PLAN.md) for detailed Kubernetes manifests.

## API Endpoints

### Monitor Spark Status
```
GET /api/v1/monitoring/spark/status
```

Response:
```json
{
  "success": true,
  "data": {
    "status": "active",
    "session_active": true,
    "app_name": "DataQuality_SaaS_Checks",
    "master": "local[*]",
    "spark_version": "3.5.0",
    "default_parallelism": 8
  }
}
```

### Get Spark Configuration
```
GET /api/v1/monitoring/spark/config
```

### Restart Spark Session (Admin)
```
POST /api/v1/monitoring/spark/restart
```

## Usage in Flows

When creating a check node in a flow, optionally specify execution mode:

```json
{
  "type": "check",
  "config": {
    "checkType": "completeness",
    "columns": ["email"],
    "pass_threshold": 99,
    "execution_mode": "spark"  // Optional: "spark" or "direct"
  }
}
```

If not specified, the system auto-selects based on dataset size.

## Performance

Expected performance improvements:

| Dataset Size | Direct Execution | Spark Execution | Improvement |
|--------------|------------------|-----------------|-------------|
| 10K rows | 0.5s | 2s | - (overhead) |
| 100K rows | 5s | 3s | 1.7x |
| 1M rows | 50s | 8s | 6.3x |
| 10M rows | 500s | 30s | 16.7x |
| 100M+ rows | Timeout | ~5 min | >10x |

## Security

### Client Data Source Access

1. **Network Security**
   - VPN/PrivateLink for enterprise clients
   - IP whitelisting via `ALLOWED_CLIENT_NETWORKS`
   - mTLS for database connections

2. **Credential Management**
   - Never store passwords in code or environment
   - Use cloud secret managers in production
   - Automatic encryption at rest

3. **Multi-tenancy**
   - Per-tenant rate limiting
   - Resource quotas
   - Connection pooling

## Troubleshooting

### Spark Session Won't Start

Check logs for initialization errors:
```bash
docker logs dq-backend-1 | grep "Spark"
```

Verify environment variables:
```bash
curl http://localhost:8000/api/v1/monitoring/spark/config
```

### Check Execution Fails

1. Check connector connectivity to data source
2. Verify JDBC drivers are available in `spark-jars/`
3. Check Spark executor logs in Spark UI (port 8080)

### Performance Issues

1. Increase executor memory: `SPARK_EXECUTOR_MEMORY=8g`
2. Add more workers: `docker-compose up --scale spark-worker-1=8`
3. Enable dynamic allocation: `SPARK_DYNAMIC_ALLOCATION_ENABLED=true`

## Monitoring

Access Spark UI:
```bash
# Docker Compose
http://localhost:8080

# Kubernetes (port-forward)
kubectl port-forward -n data-quality svc/spark-master 8080:8080
```

Metrics available:
- Active jobs
- Executor status
- Memory usage
- Task execution times

## Next Steps

1. Test with your data sources
2. Benchmark performance
3. Configure for production deployment
4. Set up monitoring and alerts
5. Review security settings

For detailed implementation plan, see [SPARK_INTEGRATION_PLAN.md](../../SPARK_INTEGRATION_PLAN.md).
