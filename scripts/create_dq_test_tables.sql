-- ============================================================
-- DQ CHECK VALIDATION TEST TABLES
-- ============================================================
-- Each table is designed to validate one check dimension
-- with data that exercises all subtypes.
-- Run against dq_test database (port 5432, user testuser).
-- ============================================================

BEGIN;

-- ============================================================
-- 1. COMPLETENESS CHECK TABLE  (7 subtypes)
-- ============================================================
-- Subtypes: null, empty, placeholder, conditional, multi_field, population, group
DROP TABLE IF EXISTS public.test_completeness CASCADE;
CREATE TABLE public.test_completeness (
    id           SERIAL PRIMARY KEY,
    -- null check: 8 filled, 2 NULL  → 80%
    col_null     VARCHAR(50),
    -- empty string check: 7 non-empty, 3 empty/whitespace/NULL → 70%
    col_empty    VARCHAR(50),
    -- placeholder check: 6 real values, 4 placeholders/NULL/empty → 60%
    col_placeholder VARCHAR(50),
    -- conditional: when status='active', col_conditional must be filled
    status       VARCHAR(20),
    col_conditional VARCHAR(50),
    -- multi_field: used together with col_null and col_empty
    -- (all-mode tested on col_null + col_empty)
    -- population: same as col_null (just different threshold expectation)
    -- group: group_key defines groups
    group_key    VARCHAR(10)
);

INSERT INTO public.test_completeness
    (id, col_null, col_empty, col_placeholder, status, col_conditional, group_key)
VALUES
    -- Row 1: everything filled, active with conditional filled
    (1,  'Alice',   'alice@test.com', 'Engineer',  'active',   '2025-01-01',  'A'),
    -- Row 2: col_null filled, col_empty is empty string, placeholder is 'N/A'
    (2,  'Bob',     '',               'N/A',       'active',   '2025-02-01',  'A'),
    -- Row 3: col_null NULL, col_empty whitespace, placeholder is 'TBD'
    (3,  NULL,      '   ',            'TBD',       'inactive', NULL,          'A'),
    -- Row 4: all filled, active + conditional filled
    (4,  'Diana',   'diana@test.com', 'Manager',   'active',   '2025-03-01',  'B'),
    -- Row 5: col_null filled, col_empty filled, placeholder is 'unknown'
    (5,  'Eve',     'eve@test.com',   'unknown',   'active',   NULL,          'B'),
    -- Row 6: col_null NULL, col_empty NULL, placeholder NULL
    (6,  NULL,      NULL,             NULL,        'inactive', NULL,          'B'),
    -- Row 7: all filled, inactive
    (7,  'Grace',   'grace@test.com', 'Analyst',   'inactive', '2025-04-01',  'C'),
    -- Row 8: filled, active + conditional filled
    (8,  'Hank',    'hank@test.com',  'Director',  'active',   '2025-05-01',  'C'),
    -- Row 9: col_null filled, col_empty is '', placeholder is '-'
    (9,  'Ivy',     '',               '-',         'active',   '2025-06-01',  'C'),
    -- Row 10: all filled
    (10, 'Jack',    'jack@test.com',  'VP',        'active',   '2025-07-01',  'C');

SELECT setval('test_completeness_id_seq', 10);


-- ============================================================
-- 2. VALIDITY CHECK TABLE  (8 subtypes)
-- ============================================================
-- Subtypes: allowed_values, range, regex, reference_lookup, business_rule, cross_field, date_logic, negative
DROP TABLE IF EXISTS public.test_validity_ref CASCADE;
DROP TABLE IF EXISTS public.test_validity CASCADE;

CREATE TABLE public.test_validity (
    id             SERIAL PRIMARY KEY,
    -- allowed_values: must be in {low, medium, high}
    priority       VARCHAR(20),
    -- range: score must be 0..100
    score          INTEGER,
    -- regex: product_code must match ^PRD-[0-9]{4}$
    product_code   VARCHAR(20),
    -- business_rule: amount > 0 AND status != 'cancelled'
    amount         NUMERIC(10,2),
    order_status   VARCHAR(20),
    -- cross_field: end_value >= start_value
    start_value    INTEGER,
    end_value      INTEGER,
    -- date_logic: ship_date must be after order_date
    order_date     DATE,
    ship_date      DATE,
    -- negative: email must NOT match ^test.*@
    email          VARCHAR(100),
    -- reference_lookup: department must exist in ref table
    department     VARCHAR(50)
);

-- Reference table for reference_lookup subtype
CREATE TABLE public.test_validity_ref (
    id    SERIAL PRIMARY KEY,
    name  VARCHAR(50) UNIQUE
);

INSERT INTO public.test_validity_ref (name)
VALUES ('Engineering'), ('Sales'), ('Marketing'), ('HR'), ('Finance');

INSERT INTO public.test_validity
    (id, priority, score, product_code, amount, order_status, start_value, end_value, order_date, ship_date, email, department)
VALUES
    -- Row 1: all valid
    (1, 'high',    85,  'PRD-1234', 150.00, 'shipped',   10, 20, '2025-01-01', '2025-01-05', 'alice@corp.com',        'Engineering'),
    -- Row 2: all valid
    (2, 'medium',  72,  'PRD-5678', 200.00, 'delivered',  5, 15, '2025-02-01', '2025-02-10', 'bob@corp.com',          'Sales'),
    -- Row 3: priority invalid ('urgent' not in list)
    (3, 'urgent',  90,  'PRD-9012', 300.00, 'shipped',    1, 10, '2025-03-01', '2025-03-03', 'carol@corp.com',        'Marketing'),
    -- Row 4: score out of range (105)
    (4, 'low',    105,  'PRD-3456', 50.00,  'pending',   20, 30, '2025-04-01', '2025-04-02', 'dave@corp.com',         'HR'),
    -- Row 5: product_code invalid (no dash)
    (5, 'high',    60,  'PRD5678',  75.00,  'shipped',    8, 12, '2025-05-01', '2025-05-04', 'eve@corp.com',          'Finance'),
    -- Row 6: amount <= 0 (business rule fail)
    (6, 'medium',  80,  'PRD-7890',  0.00,  'shipped',   15, 25, '2025-06-01', '2025-06-05', 'frank@corp.com',        'Engineering'),
    -- Row 7: status cancelled (business rule fail)
    (7, 'high',    55,  'PRD-1111', 120.00, 'cancelled',  3,  9, '2025-07-01', '2025-07-03', 'grace@corp.com',        'Sales'),
    -- Row 8: end_value < start_value (cross_field fail)
    (8, 'low',     45,  'PRD-2222', 90.00,  'shipped',   30, 20, '2025-08-01', '2025-08-06', 'hank@corp.com',         'Marketing'),
    -- Row 9: ship_date before order_date (date_logic fail)
    (9, 'medium',  78,  'PRD-3333', 110.00, 'shipped',    2,  8, '2025-09-10', '2025-09-05', 'ivy@corp.com',          'HR'),
    -- Row 10: email matches negative pattern (test.*)
    (10,'high',    92,  'PRD-4444', 250.00, 'delivered',  12, 18, '2025-10-01', '2025-10-03', 'test.user@corp.com',   'Finance'),
    -- Row 11: department not in ref table
    (11,'low',     70,  'PRD-5555', 180.00, 'pending',    6, 14, '2025-11-01', '2025-11-04', 'kent@corp.com',         'Legal'),
    -- Row 12: multiple failures: score -5, bad code, cancelled
    (12,'medium',  -5,  'INVALID',  -10.00, 'cancelled', 50, 40, '2025-12-15', '2025-12-10', 'test.admin@corp.com',  'Nonexistent');

SELECT setval('test_validity_id_seq', 12);


-- ============================================================
-- 3. UNIQUENESS CHECK TABLE  (6 subtypes)
-- ============================================================
-- Subtypes: exact, composite, scoped, cross_dataset, fuzzy, temporal
DROP TABLE IF EXISTS public.test_uniqueness_ref CASCADE;
DROP TABLE IF EXISTS public.test_uniqueness CASCADE;

CREATE TABLE public.test_uniqueness (
    id             SERIAL PRIMARY KEY,
    -- exact: email should be unique; 2 duplicates
    email          VARCHAR(100),
    -- composite: (region, product) should be unique; 1 duplicate combo
    region         VARCHAR(20),
    product        VARCHAR(50),
    -- scoped: order_id unique within each region
    order_id       INTEGER,
    -- fuzzy: company_name with near-duplicates
    company_name   VARCHAR(100),
    -- temporal: sensor_id unique within 24h window
    sensor_id      VARCHAR(20),
    reading_time   TIMESTAMP
);

-- Reference for cross_dataset uniqueness
CREATE TABLE public.test_uniqueness_ref (
    id    SERIAL PRIMARY KEY,
    email VARCHAR(100)
);

INSERT INTO public.test_uniqueness
    (id, email, region, product, order_id, company_name, sensor_id, reading_time)
VALUES
    (1,  'alice@test.com',  'US',    'Widget A',   1001, 'Acme Corp',           'S001', '2025-06-01 08:00:00'),
    (2,  'bob@test.com',    'US',    'Widget B',   1002, 'Acme Corporation',    'S002', '2025-06-01 09:00:00'),
    (3,  'carol@test.com',  'EU',    'Widget A',   1001, 'Beta Inc',            'S001', '2025-06-01 10:00:00'),
    (4,  'alice@test.com',  'EU',    'Widget B',   1002, 'Beta Incorporated',   'S003', '2025-06-01 11:00:00'),
    -- dup email (alice)
    (5,  'dave@test.com',   'US',    'Widget A',   1003, 'Gamma LLC',           'S002', '2025-06-01 12:00:00'),
    -- dup composite (US, Widget A) with row 1
    (6,  'eve@test.com',    'APAC',  'Widget C',   1001, 'Delta Ltd',           'S004', '2025-06-01 13:00:00'),
    (7,  'frank@test.com',  'APAC',  'Widget A',   1002, 'Epsilon Co',          'S001', '2025-06-02 08:00:00'),
    -- sensor S001 again within 24h of row 3
    (8,  'bob@test.com',    'EU',    'Widget C',   1003, 'Acme Corp.',          'S005', '2025-06-02 09:00:00'),
    -- dup email (bob), fuzzy match to 'Acme Corp'
    (9,  'grace@test.com',  'US',    'Widget C',   1001, 'Zeta Group',          'S006', '2025-06-02 10:00:00'),
    -- dup order_id=1001 in US scope (row 1)
    (10, 'hank@test.com',   'EU',    'Widget A',   1004, 'Eta Partners',        'S007', '2025-06-02 11:00:00');

-- Cross-dataset: alice and bob exist in both tables
INSERT INTO public.test_uniqueness_ref (email)
VALUES ('alice@test.com'), ('bob@test.com'), ('unique_ref@test.com');

SELECT setval('test_uniqueness_id_seq', 10);
SELECT setval('test_uniqueness_ref_id_seq', 3);


-- ============================================================
-- 4. CONFORMITY CHECK TABLE  (6 subtypes)
-- ============================================================
-- Subtypes: standard, regex, length, charset, case, structural
DROP TABLE IF EXISTS public.test_conformity CASCADE;
CREATE TABLE public.test_conformity (
    id               SERIAL PRIMARY KEY,
    -- standard (email): 8 valid, 2 invalid
    email            VARCHAR(100),
    -- standard (phone): 8 valid, 2 invalid
    phone            VARCHAR(30),
    -- regex: custom pattern ^INV-[0-9]{6}$
    invoice_code     VARCHAR(20),
    -- length: username 3..20 chars
    username         VARCHAR(50),
    -- charset (alpha only): first_name
    first_name       VARCHAR(50),
    -- case (upper): country_code
    country_code     VARCHAR(10),
    -- structural: part_number matches AA-9999 pattern
    part_number      VARCHAR(20)
);

INSERT INTO public.test_conformity
    (id, email, phone, invoice_code, username, first_name, country_code, part_number)
VALUES
    (1,  'alice@example.com',   '555-1234',      'INV-000001', 'alice_w',     'Alice',     'US',   'AB-1234'),
    (2,  'bob@company.org',     '555-5678',      'INV-000002', 'bob',         'Bob',       'UK',   'CD-5678'),
    (3,  'not-an-email',        '555-9012',      'INV-000003', 'carol_smith', 'Carol',     'DE',   'EF-9012'),
    -- bad email
    (4,  'dave@test.co',        'not-a-phone',   'INV-000004', 'dave_j',      'Dave',      'FR',   'GH-3456'),
    -- bad phone
    (5,  'eve@example.com',     '555-3456',      'INV-00005',  'ev',          'Eve',       'JP',   'IJ-7890'),
    -- bad invoice (5 digits), bad username (too short)
    (6,  'frank@example.com',   '555-7890',      'INV-000006', 'frank_miller','Frank123',  'us',   'KL-1234'),
    -- bad first_name (has digits), bad country_code (lowercase)
    (7,  '@invalid',            '555-0000',      'INV-000007', 'grace_h',     'Grace',     'CA',   'M1-5678'),
    -- bad email, bad structural (digit in letter slot)
    (8,  'hank@example.com',    '(555) 123-4567','INV-000008', 'hank_p',      'Hank',      'AU',   'NO-9012'),
    (9,  'ivy@example.com',     '555-1111',      'INVOICE-09', 'ivy_chen',    'Ivy',       'BR',   'PQ-3456'),
    -- bad invoice (wrong prefix)
    (10, 'jack@example.com',    '555 2222',      'INV-000010', 'a]b',         'Ja ck',     'MX',   'RS-7890');
    -- bad username (special char), bad first_name (space)

SELECT setval('test_conformity_id_seq', 10);


-- ============================================================
-- 5. CONSISTENCY CHECK TABLE  (6 subtypes)
-- ============================================================
-- Subtypes: intra_record, formula, temporal, inter_record, cross_table, aggregation
DROP TABLE IF EXISTS public.test_consistency_ref CASCADE;
DROP TABLE IF EXISTS public.test_consistency CASCADE;

CREATE TABLE public.test_consistency (
    id               SERIAL PRIMARY KEY,
    -- intra_record: if status = 'shipped' then tracking_number must be non-null
    status           VARCHAR(20),
    tracking_number  VARCHAR(50),
    -- formula: total = quantity * unit_price
    quantity         INTEGER,
    unit_price       NUMERIC(10,2),
    total            NUMERIC(10,2),
    -- temporal: start_date <= end_date
    start_date       DATE,
    end_date         DATE,
    -- inter_record: within same customer_id, currency should be consistent
    customer_id      INTEGER,
    currency         VARCHAR(3),
    -- aggregation: line_total sums match order_total per order_group
    order_group      VARCHAR(10),
    line_total       NUMERIC(10,2),
    order_total      NUMERIC(10,2)
);

INSERT INTO public.test_consistency
    (id, status, tracking_number, quantity, unit_price, total, start_date, end_date, customer_id, currency, order_group, line_total, order_total)
VALUES
    (1,  'shipped',   'TRK-001', 5,  10.00,  50.00,  '2025-01-01', '2025-01-10', 100, 'USD', 'ORD-A', 50.00,  150.00),
    (2,  'shipped',   'TRK-002', 3,  20.00,  60.00,  '2025-02-01', '2025-02-15', 100, 'USD', 'ORD-A', 60.00,  150.00),
    (3,  'shipped',   NULL,      2,  15.00,  30.00,  '2025-03-01', '2025-03-05', 100, 'EUR', 'ORD-A', 40.00,  150.00),
    -- intra fail (shipped but no tracking), inter fail (EUR vs USD for customer 100)
    (4,  'pending',   NULL,      4,  25.00, 100.00,  '2025-04-01', '2025-04-20', 200, 'GBP', 'ORD-B', 100.00, 250.00),
    (5,  'shipped',   'TRK-005', 1,  50.00,  55.00,  '2025-05-01', '2025-05-03', 200, 'GBP', 'ORD-B', 50.00,  250.00),
    -- formula fail (1*50=50 not 55)
    (6,  'delivered',  NULL,     10,   5.00,  50.00,  '2025-06-01', '2025-06-10', 200, 'GBP', 'ORD-B', 100.00, 250.00),
    (7,  'shipped',   'TRK-007', 2,  30.00,  60.00,  '2025-07-15', '2025-07-10', 300, 'JPY', 'ORD-C', 60.00,  120.00),
    -- temporal fail (end < start)
    (8,  'shipped',   'TRK-008', 3,  20.00,  60.00,  '2025-08-01', '2025-08-10', 300, 'JPY', 'ORD-C', 60.00,  120.00),
    (9,  'cancelled', NULL,      6,  10.00,  60.00,  '2025-09-01', '2025-09-15', 400, 'USD', 'ORD-D', 60.00,   60.00),
    (10, 'shipped',   'TRK-010', 8,  12.50, 100.00,  '2025-10-01', '2025-10-20', 400, 'USD', 'ORD-D', 100.00, 160.00);
    -- aggregation: ORD-D line_totals sum to 160, order_total=60 on row 9 (mismatch), =160 on row 10

SELECT setval('test_consistency_id_seq', 10);

-- Cross-table ref for consistency
CREATE TABLE public.test_consistency_ref (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER,
    currency     VARCHAR(3)
);

INSERT INTO public.test_consistency_ref (customer_id, currency)
VALUES (100, 'USD'), (200, 'GBP'), (300, 'JPY'), (400, 'USD');

SELECT setval('test_consistency_ref_id_seq', 4);


-- ============================================================
-- 6. TIMELINESS CHECK TABLE  (6 subtypes)
-- ============================================================
-- Subtypes: freshness, record_age, latency, processing_delay, delivery_window, heartbeat
DROP TABLE IF EXISTS public.test_timeliness CASCADE;
CREATE TABLE public.test_timeliness (
    id                  SERIAL PRIMARY KEY,
    -- freshness / record_age / heartbeat: updated_at
    -- 8 recent rows, 2 old rows
    updated_at          TIMESTAMP,
    -- latency: event_time vs load_time
    event_time          TIMESTAMP,
    load_time           TIMESTAMP,
    -- processing_delay: proc_start vs proc_end
    proc_start          TIMESTAMP,
    proc_end            TIMESTAMP,
    -- delivery_window: delivery_time should be between 06:00-09:00
    delivery_time       TIMESTAMP,
    -- label for readability
    description         VARCHAR(50)
);

INSERT INTO public.test_timeliness
    (id, updated_at, event_time, load_time, proc_start, proc_end, delivery_time, description)
VALUES
    -- Recent data (within 7 days of "now")
    (1,  NOW() - INTERVAL '1 hour',
         NOW() - INTERVAL '2 hours',   NOW() - INTERVAL '1 hour',
         NOW() - INTERVAL '3 hours',   NOW() - INTERVAL '2 hours 50 minutes',
         (CURRENT_DATE + TIME '07:30:00'), 'Recent, fast, in window'),

    (2,  NOW() - INTERVAL '3 hours',
         NOW() - INTERVAL '4 hours',   NOW() - INTERVAL '3 hours',
         NOW() - INTERVAL '5 hours',   NOW() - INTERVAL '4 hours 45 minutes',
         (CURRENT_DATE + TIME '08:15:00'), 'Recent, fast, in window'),

    (3,  NOW() - INTERVAL '12 hours',
         NOW() - INTERVAL '14 hours',  NOW() - INTERVAL '12 hours',
         NOW() - INTERVAL '15 hours',  NOW() - INTERVAL '14 hours 30 minutes',
         (CURRENT_DATE + TIME '06:45:00'), 'Recent, 2h latency, in window'),

    (4,  NOW() - INTERVAL '1 day',
         NOW() - INTERVAL '26 hours',  NOW() - INTERVAL '1 day',
         NOW() - INTERVAL '27 hours',  NOW() - INTERVAL '26 hours 20 minutes',
         (CURRENT_DATE + TIME '08:50:00'), '1 day old, fast, in window'),

    (5,  NOW() - INTERVAL '2 days',
         NOW() - INTERVAL '50 hours',  NOW() - INTERVAL '2 days',
         NOW() - INTERVAL '51 hours',  NOW() - INTERVAL '50 hours 10 minutes',
         (CURRENT_DATE + TIME '05:30:00'), '2 days old, fast, BEFORE window'),
    -- delivery_window fail (05:30 < 06:00)

    (6,  NOW() - INTERVAL '3 days',
         NOW() - INTERVAL '72 hours',  NOW() - INTERVAL '3 days',
         NOW() - INTERVAL '73 hours',  NOW() - INTERVAL '72 hours 5 minutes',
         (CURRENT_DATE + TIME '07:00:00'), '3 days old, fast, in window'),

    (7,  NOW() - INTERVAL '5 days',
         NOW() - INTERVAL '5 days',    NOW() - INTERVAL '5 days' + INTERVAL '3 hours',
         NOW() - INTERVAL '5 days',    NOW() - INTERVAL '5 days' + INTERVAL '2 hours',
         (CURRENT_DATE + TIME '10:30:00'), '5 days old, 3h latency, AFTER window'),
    -- latency fail (3h > 2h threshold), delivery_window fail (10:30 > 09:00)

    (8,  NOW() - INTERVAL '6 days',
         NOW() - INTERVAL '6 days',    NOW() - INTERVAL '6 days' + INTERVAL '30 minutes',
         NOW() - INTERVAL '6 days',    NOW() - INTERVAL '6 days' + INTERVAL '15 minutes',
         (CURRENT_DATE + TIME '08:00:00'), '6 days old, fast, in window'),

    -- Old data (> 30 days)
    (9,  NOW() - INTERVAL '60 days',
         NOW() - INTERVAL '60 days',   NOW() - INTERVAL '60 days' + INTERVAL '5 hours',
         NOW() - INTERVAL '60 days',   NOW() - INTERVAL '60 days' + INTERVAL '3 hours',
         (CURRENT_DATE + TIME '04:00:00'), 'Very old, 5h latency, BEFORE window'),
    -- record_age fail, latency fail, processing_delay fail (3h > 1h), delivery fail

    (10, NOW() - INTERVAL '90 days',
         NOW() - INTERVAL '90 days',   NOW() - INTERVAL '90 days' + INTERVAL '48 hours',
         NOW() - INTERVAL '90 days',   NOW() - INTERVAL '90 days' + INTERVAL '4 hours',
         (CURRENT_DATE + TIME '11:00:00'), 'Very old, 48h latency, AFTER window');
    -- record_age fail, latency fail, processing_delay fail, delivery fail

SELECT setval('test_timeliness_id_seq', 10);


-- ============================================================
-- 7. ACCURACY CHECK TABLE  (5 subtypes)
-- ============================================================
-- Subtypes: reference_comparison, trusted_source, tolerated_deviation, statistical, derived_value
DROP TABLE IF EXISTS public.test_accuracy_ref CASCADE;
DROP TABLE IF EXISTS public.test_accuracy CASCADE;

CREATE TABLE public.test_accuracy (
    id               SERIAL PRIMARY KEY,
    -- reference_comparison / trusted_source: compare name against ref
    employee_id      INTEGER UNIQUE,
    name             VARCHAR(100),
    -- tolerated_deviation: salary compared to ref (tolerance: absolute 500 or 5%)
    salary           NUMERIC(10,2),
    -- statistical: score column (z-score/IQR outlier detection)
    score            NUMERIC(10,2),
    -- derived_value: bonus = salary * rate
    bonus_rate       NUMERIC(5,4),
    bonus            NUMERIC(10,2)
);

CREATE TABLE public.test_accuracy_ref (
    id           SERIAL PRIMARY KEY,
    employee_id  INTEGER UNIQUE,
    name         VARCHAR(100),
    salary       NUMERIC(10,2)
);

-- Reference (trusted) data
INSERT INTO public.test_accuracy_ref (employee_id, name, salary)
VALUES
    (1, 'Alice Johnson',  75000.00),
    (2, 'Bob Smith',      82000.00),
    (3, 'Carol Williams', 90000.00),
    (4, 'Dave Brown',     65000.00),
    (5, 'Eve Davis',      71000.00),
    (6, 'Frank Miller',   88000.00),
    (7, 'Grace Wilson',   95000.00),
    (8, 'Hank Moore',     78000.00);

INSERT INTO public.test_accuracy
    (id, employee_id, name, salary, score, bonus_rate, bonus)
VALUES
    -- Matches reference exactly
    (1, 1, 'Alice Johnson',   75000.00,  85.00, 0.1000,  7500.00),
    -- Matches reference exactly
    (2, 2, 'Bob Smith',       82000.00,  78.00, 0.0800,  6560.00),
    -- Name mismatch (Carol vs Caroline)
    (3, 3, 'Caroline Williams', 90000.00, 92.00, 0.1200, 10800.00),
    -- Salary deviation: 64000 vs 65000 ref (1000 diff = within 5% but > 500 absolute)
    (4, 4, 'Dave Brown',      64000.00,  70.00, 0.0750,  4800.00),
    -- Matches reference
    (5, 5, 'Eve Davis',       71000.00,  88.00, 0.0900,  6390.00),
    -- Name mismatch (Frank vs Franklin), salary off by 3000
    (6, 6, 'Franklin Miller', 85000.00,  75.00, 0.1100,  9350.00),
    -- Matches reference
    (7, 7, 'Grace Wilson',    95000.00,  81.00, 0.1000,  9500.00),
    -- Matches reference
    (8, 8, 'Hank Moore',      78000.00,  83.00, 0.0850,  6630.00),
    -- Statistical outlier (score=5, way below mean ~77)
    (9, 9, 'Ivy Chen',        68000.00,   5.00, 0.0700,  4760.00),
    -- Derived value wrong: bonus should be 72000*0.12=8640, but is 9000
    (10,10,'Jack Taylor',     72000.00,  79.00, 0.1200,  9000.00);

SELECT setval('test_accuracy_id_seq', 10);
SELECT setval('test_accuracy_ref_id_seq', 8);


-- ============================================================
-- 8. RECONCILIATION CHECK TABLE  (6 subtypes)
-- ============================================================
-- Two tables: source and target, with controlled mismatches
DROP TABLE IF EXISTS public.test_recon_target CASCADE;
DROP TABLE IF EXISTS public.test_recon_source CASCADE;

CREATE TABLE public.test_recon_source (
    id          SERIAL PRIMARY KEY,
    txn_id      INTEGER UNIQUE,
    customer    VARCHAR(50),
    amount      NUMERIC(10,2),
    quantity    INTEGER,
    region      VARCHAR(20)
);

CREATE TABLE public.test_recon_target (
    id          SERIAL PRIMARY KEY,
    txn_id      INTEGER UNIQUE,
    customer    VARCHAR(50),
    amount      NUMERIC(10,2),
    quantity    INTEGER,
    region      VARCHAR(20)
);

-- Source: 10 records
INSERT INTO public.test_recon_source (txn_id, customer, amount, quantity, region)
VALUES
    (1001, 'Alice',  100.00, 5,  'US'),
    (1002, 'Bob',    200.00, 3,  'EU'),
    (1003, 'Carol',  150.00, 7,  'US'),
    (1004, 'Dave',   300.00, 2,  'APAC'),
    (1005, 'Eve',    250.00, 4,  'EU'),
    (1006, 'Frank',  175.00, 6,  'US'),
    (1007, 'Grace',  400.00, 1,  'APAC'),
    (1008, 'Hank',   125.00, 8,  'EU'),
    (1009, 'Ivy',    350.00, 3,  'US'),
    (1010, 'Jack',   275.00, 5,  'APAC');

-- Target: 9 records (missing 1010), 1 extra (1011), some field mismatches
INSERT INTO public.test_recon_target (txn_id, customer, amount, quantity, region)
VALUES
    (1001, 'Alice',  100.00, 5,  'US'),       -- exact match
    (1002, 'Bob',    200.00, 3,  'EU'),       -- exact match
    (1003, 'Carol',  155.00, 7,  'US'),       -- amount mismatch (150 vs 155, diff=5)
    (1004, 'Dave',   300.00, 2,  'APAC'),     -- exact match
    (1005, 'Eve',    250.00, 4,  'EU'),       -- exact match
    (1006, 'Frank',  175.00, 6,  'US'),       -- exact match
    (1007, 'Grace',  410.00, 1,  'APAC'),     -- amount mismatch (400 vs 410, diff=10)
    (1008, 'Henry',  125.00, 8,  'EU'),       -- customer mismatch (Hank vs Henry)
    (1009, 'Ivy',    350.00, 3,  'US'),       -- exact match
    -- 1010 missing from target (Jack)
    (1011, 'Karen',  500.00, 2,  'US');       -- extra in target

SELECT setval('test_recon_source_id_seq', 10);
SELECT setval('test_recon_target_id_seq', 10);


-- ============================================================
-- EXPECTED RESULTS TABLE
-- ============================================================
-- After running DQ flows, compare actual results against this table
DROP TABLE IF EXISTS public.dq_expected_results CASCADE;
CREATE TABLE public.dq_expected_results (
    id                SERIAL PRIMARY KEY,
    check_dimension   VARCHAR(30)   NOT NULL,
    check_subtype     VARCHAR(30)   NOT NULL,
    test_table        VARCHAR(60)   NOT NULL,
    target_column     VARCHAR(60),
    config_summary    TEXT          NOT NULL,
    total_rows        INTEGER       NOT NULL,
    expected_pass     INTEGER       NOT NULL,
    expected_fail     INTEGER       NOT NULL,
    expected_pass_rate NUMERIC(5,2) NOT NULL,
    notes             TEXT
);

INSERT INTO public.dq_expected_results
    (check_dimension, check_subtype, test_table, target_column, config_summary,
     total_rows, expected_pass, expected_fail, expected_pass_rate, notes)
VALUES
-- ==================== COMPLETENESS ====================
('completeness', 'null', 'test_completeness', 'col_null',
 'checkMode=null, columns=[col_null]',
 10, 8, 2, 80.00,
 'Rows 3,6 have NULL col_null'),

('completeness', 'empty', 'test_completeness', 'col_empty',
 'checkMode=empty, columns=[col_empty]',
 10, 6, 4, 60.00,
 'Rows 2,9 empty string; row 3 whitespace; row 6 NULL. 4 fail, 6 pass'),

('completeness', 'placeholder', 'test_completeness', 'col_placeholder',
 'checkMode=placeholder, columns=[col_placeholder], placeholderValues=[N/A,TBD,unknown,-]',
 10, 5, 5, 50.00,
 'Fail: row 2(N/A), row 3(TBD), row 5(unknown), row 6(NULL), row 9(-). Pass: rows 1,4,7,8,10'),

('completeness', 'conditional', 'test_completeness', 'col_conditional',
 'checkMode=conditional, conditionColumn=status, conditionOperator=equals, conditionValue=active',
 10, 9, 1, 90.00,
 'Active rows needing col_conditional: 1,2,4,5,8,9,10. Only row 5 missing → fail. Inactive rows 3,6,7 auto-pass. 9 pass, 1 fail'),

('completeness', 'multi_field', 'test_completeness', 'col_null,col_empty',
 'checkMode=multi_field, columns=[col_null,col_empty], multiFieldMode=all',
 10, 8, 2, 80.00,
 'multi_field NULL-only check. Only rows 3,6 have at least one NULL column → 2 fail, 8 pass'),

('completeness', 'multi_field', 'test_completeness', 'col_null,col_empty',
 'checkMode=multi_field, columns=[col_null,col_empty], multiFieldMode=any',
 10, 9, 1, 90.00,
 'At least one non-NULL: only row 6 has both NULL → 1 fail'),

('completeness', 'population', 'test_completeness', 'col_null',
 'checkMode=population, columns=[col_null], threshold_pass=70',
 10, 8, 2, 80.00,
 'Same as null check (80%) but with lower threshold (70%). PASSES threshold'),

('completeness', 'group', 'test_completeness', 'col_null',
 'checkMode=group, columns=[col_null], groupByColumns=[group_key]',
 10, 8, 2, 80.00,
 'Group A: 2/3 non-null(67%). Group B: 1/3(33%). Group C: 4/4(100%). Overall 8/10=80%. At 100% threshold, groups A and B fail'),

-- ==================== VALIDITY ====================
('validity', 'allowed_values', 'test_validity', 'priority',
 'validationType=allowed_values, columns=[priority], allowedValues=[low,medium,high]',
 12, 11, 1, 91.67,
 'Row 3 has "urgent" which is not in allowed list'),

('validity', 'range', 'test_validity', 'score',
 'validationType=range, columns=[score], minValue=0, maxValue=100',
 12, 10, 2, 83.33,
 'Row 4 score=105 (>100), row 12 score=-5 (<0)'),

('validity', 'regex', 'test_validity', 'product_code',
 'validationType=regex, columns=[product_code], pattern=^PRD-[0-9]{4}$',
 12, 10, 2, 83.33,
 'Row 5 "PRD5678" (no dash), row 12 "INVALID" (wrong format)'),

('validity', 'business_rule', 'test_validity', 'amount',
 'validationType=business_rule, businessRuleExpression="amount" > 0 AND "order_status" != ''cancelled''',
 12, 9, 3, 75.00,
 'Row 6 amount=0 (not >0), row 7 cancelled, row 12 amount=-10 AND cancelled'),

('validity', 'cross_field', 'test_validity', 'end_value',
 'validationType=cross_field, columns=[end_value], comparisonColumn=start_value, comparisonOperator=greater_equal',
 12, 10, 2, 83.33,
 'Row 8: end=20<start=30, row 12: end=40<start=50'),

('validity', 'date_logic', 'test_validity', 'ship_date',
 'validationType=date_logic, columns=[ship_date], comparisonColumn=order_date, dateOperator=after',
 12, 10, 2, 83.33,
 'Row 9: ship 09-05 < order 09-10, row 12: ship 12-10 < order 12-15'),

('validity', 'negative', 'test_validity', 'email',
 'validationType=negative, columns=[email], negativePattern=^test\., negativeMatchMode=regex',
 12, 10, 2, 83.33,
 'Row 10 "test.user@..." and row 12 "test.admin@..." match ^test\.'),

('validity', 'reference_lookup', 'test_validity', 'department',
 'validationType=reference_lookup, columns=[department], referenceDataset=test_validity_ref, referenceColumn=name',
 12, 10, 2, 83.33,
 'Row 11 "Legal" and row 12 "Nonexistent" not in ref table'),

-- ==================== UNIQUENESS ====================
('uniqueness', 'exact', 'test_uniqueness', 'email',
 'uniquenessMode=exact, columns=[email]',
 10, 6, 4, 60.00,
 'alice@test.com appears in rows 1,4 (2 dup rows). bob@test.com in rows 2,8 (2 dup rows). 4 rows involved in duplicates'),

('uniqueness', 'composite', 'test_uniqueness', 'region,product',
 'uniquenessMode=composite, columns=[region,product]',
 10, 8, 2, 80.00,
 'Duplicate combo: (US, Widget A) in rows 1,5. 2 rows involved'),

('uniqueness', 'scoped', 'test_uniqueness', 'order_id',
 'uniquenessMode=scoped, columns=[order_id], scopeColumns=[region]',
 10, 8, 2, 80.00,
 'order_id=1001 appears twice in US (rows 1,9). 2 rows involved in scope duplicate'),

('uniqueness', 'fuzzy', 'test_uniqueness', 'company_name',
 'uniquenessMode=fuzzy, columns=[company_name], fuzzyAlgorithm=levenshtein, fuzzyThreshold=0.8',
 10, 7, 3, 70.00,
 'Near-duplicates: "Acme Corp" / "Acme Corporation" / "Acme Corp." (rows 1,2,8). Depends on similarity implementation'),

('uniqueness', 'temporal', 'test_uniqueness', 'sensor_id',
 'uniquenessMode=temporal, columns=[sensor_id], temporalColumn=reading_time, temporalWindowValue=24, temporalWindowUnit=hours',
 10, 6, 4, 60.00,
 'S001 in rows 1,3,7: rows 1&3 within 24h, rows 3&7 within 24h. S002 in rows 2,5 within 24h. ~4 duplicate rows'),

-- ==================== CONFORMITY ====================
('conformity', 'standard', 'test_conformity', 'email',
 'conformityType=standard, columns=[email], standardName=email',
 10, 8, 2, 80.00,
 'Row 3 "not-an-email", row 7 "@invalid" fail email pattern ^[^@]+@[^@]+\.[^@]+$'),

('conformity', 'standard', 'test_conformity', 'phone',
 'conformityType=standard, columns=[phone], standardName=phone',
 10, 9, 1, 90.00,
 'Row 4 "not-a-phone" fails phone pattern. Others with dashes/parens/spaces may pass'),

('conformity', 'regex', 'test_conformity', 'invoice_code',
 'conformityType=regex, columns=[invoice_code], pattern=^INV-[0-9]{6}$',
 10, 7, 3, 70.00,
 'Row 5 "INV-00005" (5 digits), row 9 "INVOICE-09" (wrong prefix), row 7 might fail if code is wrong. Rows with 6-digit codes pass'),

('conformity', 'length', 'test_conformity', 'username',
 'conformityType=length, columns=[username], minLength=3, maxLength=20',
 10, 9, 1, 90.00,
 'Row 5 "ev" (2 chars < 3 min). "a]b" row 10 is 3 chars → passes length'),

('conformity', 'charset', 'test_conformity', 'first_name',
 'conformityType=charset, columns=[first_name], allowedCharset=alpha',
 10, 8, 2, 80.00,
 'Row 6 "Frank123" has digits, row 10 "Ja ck" has space. Both fail alpha-only'),

('conformity', 'case', 'test_conformity', 'country_code',
 'conformityType=case, columns=[country_code], expectedCase=upper',
 10, 9, 1, 90.00,
 'Row 6 "us" is lowercase → fails UPPER case check'),

('conformity', 'structural', 'test_conformity', 'part_number',
 'conformityType=structural, columns=[part_number], structuralPattern=AA-9999',
 10, 9, 1, 90.00,
 'Row 7 "M1-5678" has digit in letter slot. Pattern AA-9999 → ^[A-Z]{2}-[0-9]{4}$'),

-- ==================== CONSISTENCY ====================
('consistency', 'intra_record', 'test_consistency', 'tracking_number',
 'consistencyType=intra_record, ruleExpression=CASE WHEN "status" = ''shipped'' THEN "tracking_number" IS NOT NULL ELSE TRUE END',
 10, 9, 1, 90.00,
 'Row 3: shipped but tracking_number is NULL'),

('consistency', 'formula', 'test_consistency', 'total',
 'consistencyType=formula, columns=[total], ruleExpression="quantity" * "unit_price"',
 10, 9, 1, 90.00,
 'Row 5: 1*50=50 but total=55 (mismatch)'),

('consistency', 'temporal', 'test_consistency', 'end_date',
 'consistencyType=temporal, startColumn=start_date, endColumn=end_date',
 10, 9, 1, 90.00,
 'Row 7: end_date 07-10 < start_date 07-15'),

('consistency', 'inter_record', 'test_consistency', 'currency',
 'consistencyType=inter_record, columns=[currency], groupByColumns=[customer_id]',
 10, 8, 2, 80.00,
 'Customer 100: rows 1,2 USD but row 3 EUR (inconsistent). Rows 1,2 or row 3 flagged depending on majority logic. ~2 rows fail'),

('consistency', 'aggregation', 'test_consistency', 'order_total',
 'consistencyType=aggregation, columns=[line_total], aggregateFunction=SUM, expectedColumn=order_total, groupByColumns=[order_group]',
 10, 8, 2, 80.00,
 'ORD-A: sum(50+60+40)=150 vs order_total=150 ✓. ORD-D: sum(60+100)=160 vs row 9 order_total=60 ✗. ~2 rows fail'),

-- ==================== TIMELINESS ====================
('timeliness', 'freshness', 'test_timeliness', 'updated_at',
 'timelinessType=freshness, timestampColumn=updated_at, maxAgeValue=24, maxAgeUnit=hours',
 10, 10, 0, 100.00,
 'Freshness checks MAX(updated_at) vs now. Max is 1 hour ago → PASS. This is a table-level check, not row-level'),

('timeliness', 'record_age', 'test_timeliness', 'updated_at',
 'timelinessType=record_age, timestampColumn=updated_at, maxAgeValue=30, maxAgeUnit=days',
 10, 8, 2, 80.00,
 'Rows 9 (60 days) and 10 (90 days) exceed 30-day max age'),

('timeliness', 'latency', 'test_timeliness', 'load_time',
 'timelinessType=latency, eventTimestampColumn=event_time, loadTimestampColumn=load_time, maxLatencyValue=2, maxLatencyUnit=hours',
 10, 7, 3, 70.00,
 'Row 7 (3h), row 9 (5h), row 10 (48h) exceed 2h max latency'),

('timeliness', 'processing_delay', 'test_timeliness', 'proc_end',
 'timelinessType=processing_delay, startTimestampColumn=proc_start, endTimestampColumn=proc_end, maxDelayValue=60, maxDelayUnit=minutes',
 10, 7, 3, 70.00,
 'Row 7 (2h), row 9 (3h), row 10 (4h) processing delay exceeds 60 min'),

('timeliness', 'delivery_window', 'test_timeliness', 'delivery_time',
 'timelinessType=delivery_window, timestampColumn=delivery_time, windowStart=06:00, windowEnd=09:00',
 10, 6, 4, 60.00,
 'Row 5 (05:30), row 7 (10:30), row 9 (04:00), row 10 (11:00) outside 06:00-09:00'),

('timeliness', 'heartbeat', 'test_timeliness', 'updated_at',
 'timelinessType=heartbeat, timestampColumn=updated_at, expectedFrequency=1h',
 10, 10, 0, 100.00,
 'Heartbeat checks most recent timestamp. Last update 1h ago < frequency → PASS (table-level)'),

-- ==================== ACCURACY ====================
('accuracy', 'statistical', 'test_accuracy', 'score',
 'accuracyType=statistical, columns=[score], statisticalMethod=zscore, statisticalThreshold=3.0',
 10, 9, 1, 90.00,
 'Scores: 85,78,92,70,88,75,81,83,5,79. Mean≈73.6, StdDev≈24.7. Row 9 score=5 → z≈-2.78. Close to threshold. With exact z-score row 9 may pass or fail depending on implementation'),

('accuracy', 'statistical', 'test_accuracy', 'score',
 'accuracyType=statistical, columns=[score], statisticalMethod=iqr, outlierThreshold=1.5',
 10, 9, 1, 90.00,
 'Q1≈75, Q3≈85, IQR=10. Lower=75-15=60, Upper=85+15=100. Row 9 score=5 < 60 → outlier'),

('accuracy', 'derived_value', 'test_accuracy', 'bonus',
 'accuracyType=derived_value, columns=[bonus], formula="salary" * "bonus_rate", toleranceType=none',
 10, 9, 1, 90.00,
 'Row 10: salary*rate=72000*0.12=8640, but bonus=9000 (diff=360). All others correct'),

('accuracy', 'reference_comparison', 'test_accuracy', 'name',
 'accuracyType=reference_comparison, columns=[name], referenceDataset=test_accuracy_ref, joinKeys=[employee_id]',
 8, 6, 2, 75.00,
 'Row 3: "Caroline Williams" vs "Carol Williams". Row 6: "Franklin Miller" vs "Frank Miller". Rows 9,10 have no ref match (not compared). 8 joined rows, 6 match'),

('accuracy', 'tolerated_deviation', 'test_accuracy', 'salary',
 'accuracyType=tolerated_deviation, columns=[salary], referenceDataset=test_accuracy_ref, joinKeys=[employee_id], toleranceType=absolute, toleranceValue=1000',
 8, 7, 1, 87.50,
 'Row 6: |85000-88000|=3000 > 1000 tolerance. Row 4: |64000-65000|=1000 = tolerance (passes if inclusive). 8 joined rows'),

-- ==================== RECONCILIATION ====================
('reconciliation', 'record_count', 'test_recon_source,test_recon_target', NULL,
 'reconciliationType=record_count, sourceDataset=test_recon_source, targetDataset=test_recon_target',
 10, 10, 0, 100.00,
 'Source=10, Target=10. Counts match → 100%. (min/max ratio = 10/10)'),

('reconciliation', 'one_to_one', 'test_recon_source,test_recon_target', NULL,
 'reconciliationType=one_to_one, sourceDataset=test_recon_source, targetDataset=test_recon_target, joinKeys=[txn_id]',
 11, 9, 2, 81.82,
 'FULL OUTER JOIN: 9 matched, 1 missing in target (1010), 1 extra in target (1011). max(10,10)=10 but union=11 total slots, 9 matched → 9/11=81.8%'),

('reconciliation', 'field_level', 'test_recon_source,test_recon_target', NULL,
 'reconciliationType=field_level, sourceDataset=test_recon_source, targetDataset=test_recon_target, joinKeys=[txn_id], compareColumns=[customer,amount]',
 9, 6, 3, 66.67,
 'Joined on txn_id: 9 matches. Mismatches: row 1003 amount, row 1007 amount, row 1008 customer. 6 full field match'),

('reconciliation', 'aggregate', 'test_recon_source,test_recon_target', NULL,
 'reconciliationType=aggregate, sourceDataset=test_recon_source, targetDataset=test_recon_target, aggregateColumn=amount, aggregateFunction=SUM',
 1, 0, 1, 0.00,
 'Source SUM(amount)=2325, Target SUM(amount)=2365. Not equal → 0% (or ratio-based)'),

('reconciliation', 'tolerance', 'test_recon_source,test_recon_target', NULL,
 'reconciliationType=tolerance, sourceDataset=test_recon_source, targetDataset=test_recon_target, joinKeys=[txn_id], compareColumn=amount, toleranceType=absolute, toleranceValue=6',
 9, 8, 1, 88.89,
 'Joined: 9 rows. Diffs: 1003=5 (within 6), 1007=10 (exceeds 6). 8 within tolerance, 1 outside'),

('reconciliation', 'missing_extra', 'test_recon_source,test_recon_target', NULL,
 'reconciliationType=missing_extra, sourceDataset=test_recon_source, targetDataset=test_recon_target, joinKeys=[txn_id]',
 11, 9, 2, 81.82,
 'Missing in target: txn_id=1010 (Jack). Extra in target: txn_id=1011 (Karen). 9 matched / max(10,10) slots');

SELECT setval('dq_expected_results_id_seq', (SELECT MAX(id) FROM public.dq_expected_results));

COMMIT;

-- Quick verification
SELECT check_dimension, COUNT(*) as subtypes FROM public.dq_expected_results
GROUP BY check_dimension ORDER BY check_dimension;
