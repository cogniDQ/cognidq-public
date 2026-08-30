-- ============================================================================
-- 034: Seed realistic test data for NL Rule Builder testing
-- ============================================================================
-- Creates:
--   - 1 data source (E-Commerce Production DB)
--   - 5 datasets (customers, orders, order_lines, products, shipments)
--   - ~50 dataset fields with business definitions
--   - 15 glossary terms with synonyms
-- ============================================================================

-- Constants
DO $$
DECLARE
    v_ws_id     UUID := '00000000-0000-0000-0000-000000000020';
    v_tenant_id UUID := '8062ed84-5660-4470-833c-f748ed0a7481';
    v_actor_id  UUID := '63cae557-c3bc-4442-8592-58205e772aa6';
    v_ds_id     UUID := 'a0000000-0000-0000-0000-000000000001';
    v_cust_id   UUID := 'b0000000-0000-0000-0000-000000000001';
    v_ord_id    UUID := 'b0000000-0000-0000-0000-000000000002';
    v_line_id   UUID := 'b0000000-0000-0000-0000-000000000003';
    v_prod_id   UUID := 'b0000000-0000-0000-0000-000000000004';
    v_ship_id   UUID := 'b0000000-0000-0000-0000-000000000005';
BEGIN

-- ── Data Source ──────────────────────────────────────────────────────────────
INSERT INTO control.data_sources (
    data_source_id, workspace_id, tenant_id, source_name, source_type,
    connection_mode, environment, description, status,
    last_test_status, created_by
) VALUES (
    v_ds_id, v_ws_id, v_tenant_id,
    'E-Commerce Production DB', 'postgresql',
    'direct', 'production',
    'Primary e-commerce transactional database with customer, order, product and shipment data',
    'active', 'reachable', v_actor_id
) ON CONFLICT DO NOTHING;

-- ── Dataset: customers ──────────────────────────────────────────────────────
INSERT INTO control.datasets (
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier, schema_name,
    description, business_domain, criticality, status,
    created_by, activated_at
) VALUES (
    v_cust_id, v_ws_id, v_tenant_id, v_ds_id,
    'Customers', 'table', 'customers', 'ecommerce',
    'Master customer table with personal info, contact details, and account status',
    'Customer Management', 'critical', 'active',
    v_actor_id, now()
) ON CONFLICT DO NOTHING;

INSERT INTO control.dataset_fields (field_id, dataset_id, field_name, data_type, nullable, business_definition, is_key_candidate, ordinal_position) VALUES
  (gen_random_uuid(), v_cust_id, 'customer_id',       'uuid',                    false, 'Unique customer identifier (primary key)',             true,  1),
  (gen_random_uuid(), v_cust_id, 'email',             'varchar(255)',            false, 'Customer email address, used for login and notifications', true, 2),
  (gen_random_uuid(), v_cust_id, 'first_name',        'varchar(100)',            false, 'Customer first/given name',                            false, 3),
  (gen_random_uuid(), v_cust_id, 'last_name',         'varchar(100)',            false, 'Customer last/family name',                            false, 4),
  (gen_random_uuid(), v_cust_id, 'phone',             'varchar(20)',             true,  'Customer phone number in E.164 format',                false, 5),
  (gen_random_uuid(), v_cust_id, 'date_of_birth',     'date',                    true,  'Customer date of birth for age verification',          false, 6),
  (gen_random_uuid(), v_cust_id, 'country_code',      'char(2)',                 false, 'ISO 3166-1 alpha-2 country code',                     false, 7),
  (gen_random_uuid(), v_cust_id, 'status',            'varchar(20)',             false, 'Account status: active, suspended, closed',            false, 8),
  (gen_random_uuid(), v_cust_id, 'created_at',        'timestamptz',             false, 'Account creation timestamp',                           false, 9),
  (gen_random_uuid(), v_cust_id, 'updated_at',        'timestamptz',             false, 'Last profile update timestamp',                        false, 10),
  (gen_random_uuid(), v_cust_id, 'loyalty_tier',      'varchar(20)',             true,  'Loyalty program tier: bronze, silver, gold, platinum', false, 11),
  (gen_random_uuid(), v_cust_id, 'total_lifetime_value', 'numeric(12,2)',        true,  'Total lifetime customer value in USD',                 false, 12)
ON CONFLICT DO NOTHING;

-- ── Dataset: orders ─────────────────────────────────────────────────────────
INSERT INTO control.datasets (
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier, schema_name,
    description, business_domain, criticality, status,
    created_by, activated_at
) VALUES (
    v_ord_id, v_ws_id, v_tenant_id, v_ds_id,
    'Orders', 'table', 'orders', 'ecommerce',
    'Sales order headers with customer reference, dates, status and total amounts',
    'Sales', 'critical', 'active',
    v_actor_id, now()
) ON CONFLICT DO NOTHING;

INSERT INTO control.dataset_fields (field_id, dataset_id, field_name, data_type, nullable, business_definition, is_key_candidate, ordinal_position) VALUES
  (gen_random_uuid(), v_ord_id, 'order_id',          'uuid',          false, 'Unique order identifier (primary key)',                 true,  1),
  (gen_random_uuid(), v_ord_id, 'customer_id',       'uuid',          false, 'FK to customers table',                                false, 2),
  (gen_random_uuid(), v_ord_id, 'order_date',        'date',          false, 'Date the order was placed',                            false, 3),
  (gen_random_uuid(), v_ord_id, 'shipping_date',     'date',          true,  'Date the order was shipped (null if not yet shipped)',  false, 4),
  (gen_random_uuid(), v_ord_id, 'delivery_date',     'date',          true,  'Date the order was delivered (null if not yet delivered)', false, 5),
  (gen_random_uuid(), v_ord_id, 'status',            'varchar(20)',   false, 'Order status: pending, confirmed, processing, shipped, delivered, cancelled, refunded', false, 6),
  (gen_random_uuid(), v_ord_id, 'payment_method',    'varchar(30)',   false, 'Payment method: credit_card, debit_card, paypal, bank_transfer, crypto', false, 7),
  (gen_random_uuid(), v_ord_id, 'subtotal',          'numeric(12,2)', false, 'Order subtotal before tax and shipping',               false, 8),
  (gen_random_uuid(), v_ord_id, 'tax_amount',        'numeric(12,2)', false, 'Tax amount',                                           false, 9),
  (gen_random_uuid(), v_ord_id, 'shipping_cost',     'numeric(12,2)', false, 'Shipping cost',                                        false, 10),
  (gen_random_uuid(), v_ord_id, 'total_amount',      'numeric(12,2)', false, 'Total order amount (subtotal + tax + shipping)',        false, 11),
  (gen_random_uuid(), v_ord_id, 'currency',          'char(3)',       false, 'ISO 4217 currency code (e.g. USD, EUR, GBP)',          false, 12),
  (gen_random_uuid(), v_ord_id, 'discount_pct',      'numeric(5,2)',  true,  'Discount percentage applied (0-100)',                   false, 13),
  (gen_random_uuid(), v_ord_id, 'created_at',        'timestamptz',   false, 'Order creation timestamp',                             false, 14)
ON CONFLICT DO NOTHING;

-- ── Dataset: order_lines ────────────────────────────────────────────────────
INSERT INTO control.datasets (
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier, schema_name,
    description, business_domain, criticality, status,
    created_by, activated_at
) VALUES (
    v_line_id, v_ws_id, v_tenant_id, v_ds_id,
    'Order Lines', 'table', 'order_lines', 'ecommerce',
    'Individual line items within each order, with product reference, quantity and price',
    'Sales', 'high', 'active',
    v_actor_id, now()
) ON CONFLICT DO NOTHING;

INSERT INTO control.dataset_fields (field_id, dataset_id, field_name, data_type, nullable, business_definition, is_key_candidate, ordinal_position) VALUES
  (gen_random_uuid(), v_line_id, 'line_id',          'uuid',          false, 'Unique line item identifier',                          true,  1),
  (gen_random_uuid(), v_line_id, 'order_id',         'uuid',          false, 'FK to orders table',                                   false, 2),
  (gen_random_uuid(), v_line_id, 'product_id',       'uuid',          false, 'FK to products table',                                 false, 3),
  (gen_random_uuid(), v_line_id, 'quantity',          'integer',       false, 'Quantity ordered (must be >= 1)',                       false, 4),
  (gen_random_uuid(), v_line_id, 'unit_price',        'numeric(10,2)', false, 'Price per unit at time of purchase',                   false, 5),
  (gen_random_uuid(), v_line_id, 'line_total',        'numeric(12,2)', false, 'Line total = quantity * unit_price',                   false, 6),
  (gen_random_uuid(), v_line_id, 'discount_amount',   'numeric(10,2)', true,  'Line-level discount amount',                           false, 7),
  (gen_random_uuid(), v_line_id, 'line_number',       'integer',       false, 'Sequential line number within the order',              false, 8)
ON CONFLICT DO NOTHING;

-- ── Dataset: products ───────────────────────────────────────────────────────
INSERT INTO control.datasets (
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier, schema_name,
    description, business_domain, criticality, status,
    created_by, activated_at
) VALUES (
    v_prod_id, v_ws_id, v_tenant_id, v_ds_id,
    'Products', 'table', 'products', 'ecommerce',
    'Product catalog with pricing, category and inventory information',
    'Product Management', 'high', 'active',
    v_actor_id, now()
) ON CONFLICT DO NOTHING;

INSERT INTO control.dataset_fields (field_id, dataset_id, field_name, data_type, nullable, business_definition, is_key_candidate, ordinal_position) VALUES
  (gen_random_uuid(), v_prod_id, 'product_id',       'uuid',          false, 'Unique product identifier (primary key)',              true,  1),
  (gen_random_uuid(), v_prod_id, 'sku',              'varchar(50)',   false, 'Stock Keeping Unit — unique product code',             true,  2),
  (gen_random_uuid(), v_prod_id, 'product_name',     'varchar(200)',  false, 'Product display name',                                 false, 3),
  (gen_random_uuid(), v_prod_id, 'category',         'varchar(100)',  false, 'Product category: electronics, clothing, food, home, sports', false, 4),
  (gen_random_uuid(), v_prod_id, 'price',            'numeric(10,2)', false, 'Current retail price',                                 false, 5),
  (gen_random_uuid(), v_prod_id, 'cost',             'numeric(10,2)', false, 'Cost of goods sold (purchase/manufacturing cost)',      false, 6),
  (gen_random_uuid(), v_prod_id, 'stock_quantity',   'integer',       false, 'Current stock quantity on hand',                        false, 7),
  (gen_random_uuid(), v_prod_id, 'reorder_level',    'integer',       false, 'Minimum stock level before reorder trigger',           false, 8),
  (gen_random_uuid(), v_prod_id, 'weight_kg',        'numeric(8,3)',  true,  'Product weight in kilograms',                          false, 9),
  (gen_random_uuid(), v_prod_id, 'is_active',        'boolean',       false, 'Whether the product is currently listed for sale',     false, 10),
  (gen_random_uuid(), v_prod_id, 'created_at',       'timestamptz',   false, 'Product record creation date',                         false, 11),
  (gen_random_uuid(), v_prod_id, 'discontinued_at',  'timestamptz',   true,  'Date when product was discontinued (null if active)',   false, 12)
ON CONFLICT DO NOTHING;

-- ── Dataset: shipments ──────────────────────────────────────────────────────
INSERT INTO control.datasets (
    dataset_id, workspace_id, tenant_id, data_source_id,
    dataset_name, dataset_type, physical_identifier, schema_name,
    description, business_domain, criticality, status,
    created_by, activated_at
) VALUES (
    v_ship_id, v_ws_id, v_tenant_id, v_ds_id,
    'Shipments', 'table', 'shipments', 'ecommerce',
    'Shipment tracking records with carrier, tracking number, and delivery status',
    'Logistics', 'high', 'active',
    v_actor_id, now()
) ON CONFLICT DO NOTHING;

INSERT INTO control.dataset_fields (field_id, dataset_id, field_name, data_type, nullable, business_definition, is_key_candidate, ordinal_position) VALUES
  (gen_random_uuid(), v_ship_id, 'shipment_id',      'uuid',          false, 'Unique shipment identifier',                           true,  1),
  (gen_random_uuid(), v_ship_id, 'order_id',         'uuid',          false, 'FK to orders table',                                   false, 2),
  (gen_random_uuid(), v_ship_id, 'carrier',          'varchar(50)',   false, 'Shipping carrier: fedex, ups, dhl, usps',              false, 3),
  (gen_random_uuid(), v_ship_id, 'tracking_number',  'varchar(100)',  true,  'Carrier tracking number',                              false, 4),
  (gen_random_uuid(), v_ship_id, 'shipped_at',       'timestamptz',   true,  'Timestamp when shipment was dispatched',               false, 5),
  (gen_random_uuid(), v_ship_id, 'estimated_delivery', 'date',        true,  'Estimated delivery date from carrier',                 false, 6),
  (gen_random_uuid(), v_ship_id, 'actual_delivery',  'date',          true,  'Actual delivery date (null if not yet delivered)',      false, 7),
  (gen_random_uuid(), v_ship_id, 'status',           'varchar(20)',   false, 'Shipment status: pending, in_transit, delivered, returned, lost', false, 8),
  (gen_random_uuid(), v_ship_id, 'weight_kg',        'numeric(8,3)',  true,  'Total shipment weight in kilograms',                   false, 9)
ON CONFLICT DO NOTHING;

-- ── Glossary Terms ──────────────────────────────────────────────────────────
INSERT INTO control.metadata_term_index (workspace_id, business_name, technical_name, definition, synonyms, domain, trust_level) VALUES
  (v_ws_id, 'Customer',          'customers',        'A person or organization that purchases goods or services',       '["client","buyer","account holder"]',   'Customer Management',  'authoritative'),
  (v_ws_id, 'Order',             'orders',           'A confirmed request to purchase one or more products',            '["purchase order","sales order","transaction"]', 'Sales', 'authoritative'),
  (v_ws_id, 'SKU',               'sku',              'Stock Keeping Unit — a unique identifier for each product variant', '["product code","item number","article number"]', 'Product Management', 'authoritative'),
  (v_ws_id, 'Total Amount',      'total_amount',     'The final order amount including subtotal, tax and shipping',     '["order total","grand total","final amount"]', 'Sales', 'high'),
  (v_ws_id, 'Lifetime Value',    'total_lifetime_value', 'The total revenue a customer has generated over their entire relationship', '["LTV","CLV","customer value"]', 'Customer Management', 'high'),
  (v_ws_id, 'Shipping Date',     'shipping_date',    'The date an order was dispatched from the warehouse',             '["dispatch date","ship date","send date"]', 'Logistics', 'high'),
  (v_ws_id, 'Delivery Date',     'delivery_date',    'The date an order was received by the customer',                  '["received date","arrival date"]',      'Logistics', 'high'),
  (v_ws_id, 'Payment Method',    'payment_method',   'The method used by the customer to pay for their order',          '["payment type","payment channel"]',    'Sales', 'high'),
  (v_ws_id, 'Country Code',      'country_code',     'ISO 3166-1 alpha-2 country code identifying the customer country', '["country","region code"]', 'Customer Management', 'authoritative'),
  (v_ws_id, 'Loyalty Tier',      'loyalty_tier',     'The customer loyalty program tier based on purchase history',      '["membership level","rewards tier","VIP level"]', 'Customer Management', 'high'),
  (v_ws_id, 'Discount',          'discount_pct',     'Percentage discount applied to an order or line item',            '["rebate","markdown","price reduction"]', 'Sales', 'medium'),
  (v_ws_id, 'Reorder Level',     'reorder_level',    'The minimum stock quantity that triggers a purchase order',        '["reorder point","safety stock","minimum stock"]', 'Product Management', 'high'),
  (v_ws_id, 'Carrier',           'carrier',          'The logistics company responsible for delivering the shipment',   '["shipping company","courier","logistics provider"]', 'Logistics', 'high'),
  (v_ws_id, 'E.164 Format',      NULL,               'International phone number format: + country code followed by subscriber number, e.g. +14155551234', '["international phone format","phone number standard"]', 'Standards', 'authoritative'),
  (v_ws_id, 'ISO 4217',          NULL,               'Three-letter currency code standard, e.g. USD, EUR, GBP',         '["currency code","money code"]',        'Standards', 'authoritative')
ON CONFLICT DO NOTHING;

END $$;

COMMENT ON TABLE control.metadata_term_index IS 'Business glossary terms for metadata search and NL Rule Builder context';
