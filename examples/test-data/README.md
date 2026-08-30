# Test Data Files

This directory contains sample data files for testing the Data Ingestion feature.

## Sample CSV File

### customer_data.csv

A sample customer dataset with various data types for testing:
- String columns (name, email, city)
- Integer columns (customer_id, age, orders_count)
- Float columns (total_spent, avg_order_value)
- Boolean column (is_premium)
- Date column (registration_date)

**Rows:** 10  
**Columns:** 9

Use this file to test:
- CSV parsing
- Type inference
- Data profiling
- Column statistics
- Null handling
- Upload functionality

## How to Use

1. Navigate to `/hub/ingestion` in the application
2. Drag and drop `customer_data.csv` onto the upload area
3. View the parsed data preview
4. Click "Profile Data" to see detailed statistics
5. Review suggested quality checks

## Expected Results

After upload, you should see:
- **customer_id**: integer, unique, no nulls
- **name**: string, 10 unique values
- **email**: string, 10 unique values  
- **age**: integer, some nulls expected
- **city**: string, lower cardinality
- **total_spent**: float, numeric statistics
- **avg_order_value**: float, numeric statistics
- **orders_count**: integer, numeric statistics
- **is_premium**: boolean, true/false values
- **registration_date**: date, chronological values

## Other Test Scenarios

You can also test with:
- Your own CSV files
- Excel files (.xlsx, .xls)
- JSON files (.json, .jsonl)
- Parquet files (.parquet)

Maximum file size: 100 MB
