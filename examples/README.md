# Example Data Quality Rules

This directory contains example business rules and their transformations.

## Example 1: Inactive Employee Manager Check

### Business Rule
```
An inactive employee should not have a manager assigned
```

### Generated SQL
```sql
SELECT 
    employee_id,
    employee_name,
    status,
    manager_id
FROM employees
WHERE status = 'INACTIVE'
  AND manager_id IS NOT NULL
LIMIT 1000;
```

### Expected Violations
- E003: Bob Johnson (INACTIVE with manager E100)
- E006: Eva Davis (INACTIVE with manager E102)

---

## Example 2: Customer Email Validation

### Business Rule
```
All active customers must have a valid email address
```

### Generated SQL
```sql
SELECT 
    customer_id,
    customer_name,
    email,
    status
FROM customers
WHERE status = 'ACTIVE'
  AND (
    email IS NULL 
    OR email NOT LIKE '%_@__%.__%'
  )
LIMIT 1000;
```

### Expected Violations
- C002: Tech Solutions (no email)
- C004: Startup Inc (invalid email format)

---

## Example 3: Order Amount Validation

### Business Rule
```
Sales amount should never be negative
```

### Generated SQL
```sql
SELECT 
    order_id,
    customer_id,
    amount,
    order_date,
    status
FROM orders
WHERE amount < 0
LIMIT 1000;
```

### Expected Violations
- O002: -$50.00 order

---

## Example 4: Referential Integrity

### Business Rule
```
Every order must have a valid customer ID
```

### Generated SQL
```sql
SELECT 
    o.order_id,
    o.customer_id,
    o.amount,
    o.order_date
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL
LIMIT 1000;
```

### Expected Violations
- O005: Order with customer_id 'C999' (doesn't exist)

---

## Testing These Rules

1. Start the application:
```bash
docker-compose up -d
```

2. Open the Rule Builder at http://localhost:5173/builder

3. Enter any of the business rules above

4. Click "Generate Rule" to see the SQL

5. (In production) Click "Execute" to see violations

---

## API Testing with curl

### Parse a prompt:
```bash
curl -X POST http://localhost:8000/api/v1/rules/parse \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "An inactive employee should not have a manager assigned"
  }'
```

### Generate a rule:
```bash
curl -X POST http://localhost:8000/api/v1/rules/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "An inactive employee should not have a manager assigned",
    "datasource": {
      "connection_id": "demo_001",
      "type": "postgresql",
      "database": "dataquality_db",
      "schema_name": "public",
      "table": "employees"
    },
    "severity": "ERROR"
  }'
```

### Search glossary:
```bash
curl -X POST http://localhost:8000/api/v1/glossary/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "employee",
    "limit": 5
  }'
```
