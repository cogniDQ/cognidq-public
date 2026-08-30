-- Initialize database with sample data

-- Create employees table
CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(20) PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    manager_id VARCHAR(20),
    department VARCHAR(50),
    hire_date DATE,
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create customers table
CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    status VARCHAR(20) NOT NULL,
    phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create orders table
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(20),
    amount DECIMAL(10, 2),
    order_date DATE,
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- Insert sample employees (some with violations)
INSERT INTO employees (employee_id, employee_name, status, manager_id, department, hire_date, email) VALUES
('E001', 'John Doe', 'ACTIVE', 'E100', 'Engineering', '2020-01-15', 'john.doe@company.com'),
('E002', 'Jane Smith', 'ACTIVE', 'E100', 'Engineering', '2020-03-20', 'jane.smith@company.com'),
('E003', 'Bob Johnson', 'INACTIVE', 'E100', 'HR', '2019-05-10', 'bob.johnson@company.com'),  -- VIOLATION: inactive with manager
('E004', 'Alice Williams', 'ACTIVE', 'E101', 'Sales', '2021-02-14', 'alice.williams@company.com'),
('E005', 'Charlie Brown', 'INACTIVE', NULL, 'Marketing', '2018-07-22', 'charlie.brown@company.com'),  -- OK: inactive without manager
('E006', 'Eva Davis', 'INACTIVE', 'E102', 'Finance', '2019-11-30', 'eva.davis@company.com'),  -- VIOLATION: inactive with manager
('E100', 'Manager One', 'ACTIVE', NULL, 'Engineering', '2015-01-01', 'manager.one@company.com'),
('E101', 'Manager Two', 'ACTIVE', NULL, 'Sales', '2016-03-15', 'manager.two@company.com'),
('E102', 'Manager Three', 'ACTIVE', NULL, 'Finance', '2017-06-20', 'manager.three@company.com')
ON CONFLICT (employee_id) DO NOTHING;

-- Insert sample customers (some with violations)
INSERT INTO customers (customer_id, customer_name, email, status, phone) VALUES
('C001', 'Acme Corp', 'contact@acme.com', 'ACTIVE', '555-0001'),
('C002', 'Tech Solutions', NULL, 'ACTIVE', '555-0002'),  -- VIOLATION: active customer without email
('C003', 'Global Industries', 'info@global.com', 'ACTIVE', '555-0003'),
('C004', 'Startup Inc', 'hello@startup', 'ACTIVE', '555-0004'),  -- VIOLATION: invalid email format
('C005', 'Enterprise LLC', 'contact@enterprise.com', 'INACTIVE', '555-0005'),
('C999', 'Invalid Customer', 'invalid@test.com', 'ACTIVE', '555-9999')  -- For testing foreign key violations
ON CONFLICT (customer_id) DO NOTHING;

-- Insert sample orders (some with violations)
INSERT INTO orders (order_id, customer_id, amount, order_date, status) VALUES
('O001', 'C001', 1500.00, '2026-01-05', 'COMPLETED'),
('O002', 'C002', -50.00, '2026-01-06', 'PENDING'),  -- VIOLATION: negative amount
('O003', 'C003', 3200.00, '2026-01-07', 'COMPLETED'),
('O004', 'C001', 750.00, '2026-01-08', 'COMPLETED'),
('O005', 'C999', 1000.00, '2026-01-09', 'PENDING')  -- VIOLATION: invalid customer_id
ON CONFLICT (order_id) DO NOTHING;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
