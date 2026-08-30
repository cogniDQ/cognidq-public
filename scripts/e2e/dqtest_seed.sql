CREATE SCHEMA IF NOT EXISTS enterprise_qa;

CREATE TABLE IF NOT EXISTS enterprise_qa.customer_master (
    customer_id BIGINT PRIMARY KEY,
    customer_email TEXT,
    customer_status TEXT,
    country_code TEXT,
    created_at TIMESTAMP,
    total_lifetime_value NUMERIC(18,2)
);

CREATE TABLE IF NOT EXISTS enterprise_qa.order_fact (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    order_amount NUMERIC(18,2),
    total_amount NUMERIC(18,2),
    order_date DATE,
    shipping_date DATE,
    order_status TEXT
);

CREATE TABLE IF NOT EXISTS enterprise_qa.invoice_fact (
    invoice_id BIGINT PRIMARY KEY,
    order_id BIGINT,
    invoice_amount NUMERIC(18,2),
    total_amount NUMERIC(18,2),
    invoice_date DATE,
    payment_status TEXT
);

INSERT INTO enterprise_qa.customer_master (customer_id, customer_email, customer_status, country_code, created_at, total_lifetime_value)
VALUES
    (1001, 'alice@corp.com', 'ACTIVE', 'US', NOW() - INTERVAL '100 days', 12500.50),
    (1002, 'bob@corp.com', 'ACTIVE', 'GB', NOW() - INTERVAL '60 days', 9800.00),
    (1003, NULL, 'SUSPENDED', 'DE', NOW() - INTERVAL '30 days', 1200.75),
    (1004, 'diana@corp.com', 'ACTIVE', 'US', NOW() - INTERVAL '10 days', 450.20)
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO enterprise_qa.order_fact (order_id, customer_id, order_amount, total_amount, order_date, shipping_date, order_status)
VALUES
    (5001, 1001, 100.00, 100.00, CURRENT_DATE - INTERVAL '5 days', CURRENT_DATE - INTERVAL '3 days', 'SHIPPED'),
    (5002, 1002, 250.00, 250.00, CURRENT_DATE - INTERVAL '4 days', CURRENT_DATE - INTERVAL '2 days', 'SHIPPED'),
    (5003, 1003, 175.50, 170.00, CURRENT_DATE - INTERVAL '3 days', CURRENT_DATE - INTERVAL '1 days', 'SHIPPED'),
    (5004, 1004, 80.00, 80.00, CURRENT_DATE - INTERVAL '2 days', CURRENT_DATE - INTERVAL '1 days', 'SHIPPED')
ON CONFLICT (order_id) DO NOTHING;

INSERT INTO enterprise_qa.invoice_fact (invoice_id, order_id, invoice_amount, total_amount, invoice_date, payment_status)
VALUES
    (9001, 5001, 100.00, 100.00, CURRENT_DATE - INTERVAL '4 days', 'PAID'),
    (9002, 5002, 250.00, 250.00, CURRENT_DATE - INTERVAL '3 days', 'PAID'),
    (9003, 5003, 175.50, 170.00, CURRENT_DATE - INTERVAL '2 days', 'PENDING')
ON CONFLICT (invoice_id) DO NOTHING;
