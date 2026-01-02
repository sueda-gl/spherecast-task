-- Reset SphereCast database to pristine state
BEGIN TRANSACTION;

-- Drop existing tables if they exist
DROP TABLE IF EXISTS purchase_order_line;
DROP TABLE IF EXISTS purchase_order;
DROP TABLE IF EXISTS supplier_product;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS supplier;

-- Create tables
CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    sku VARCHAR NOT NULL,
    title VARCHAR
);

CREATE TABLE supplier (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR
);

CREATE TABLE supplier_product (
    supplier_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    supplier_sku VARCHAR,
    price_per_unit FLOAT,
    PRIMARY KEY (supplier_id, product_id),
    FOREIGN KEY (supplier_id) REFERENCES supplier(id),
    FOREIGN KEY (product_id) REFERENCES product(id)
);

CREATE TABLE purchase_order (
    id INTEGER PRIMARY KEY,
    reference_num VARCHAR,
    supplier_id INTEGER NOT NULL,
    delivery_date DATE,
    external_reference VARCHAR,
    terms TEXT,
    notes TEXT,
    FOREIGN KEY (supplier_id) REFERENCES supplier(id)
);

CREATE TABLE purchase_order_line (
    id INTEGER PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    delivery_date DATE,
    notes TEXT,
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_order(id),
    FOREIGN KEY (product_id) REFERENCES product(id)
);

-- Insert pristine seed data
INSERT INTO product (id, sku, title) VALUES
    (1, 'SKU-1', 'PRODUCT ONE | GLOBAL VERSION'),
    (2, 'SKU-2', 'PRODUCT TWO with Vitamin A, B, C'),
    (3, 'SKU-3', '-'),
    (4, 'SKU-4', '(Test) Internal test for v2 of SKU-2'),
    (5, 'SKU-1-3', 'PRODUCT ONE | GLOBAL VERSION updated v3');

INSERT INTO supplier (id, name, email) VALUES
    (1, 'Big Supplier', 'big@supplier.com'),
    (2, 'Small Supplier', 'small@supplier.com');

INSERT INTO supplier_product (supplier_id, product_id, supplier_sku, price_per_unit) VALUES
    (1, 1, NULL, 1),
    (1, 2, NULL, 1),
    (1, 3, NULL, 1),
    (1, 5, 'SKU13', 2),
    (2, 1, NULL, 1);

INSERT INTO purchase_order (id, reference_num, supplier_id, delivery_date, external_reference, terms, notes) VALUES
    (1, 'PO-12', 1, '2026-01-15', NULL, NULL, NULL),
    (2, 'PO-22', 1, '2026-01-15', NULL, NULL, NULL),
    (3, 'PO-35', 2, '2026-01-15', NULL, NULL, NULL);

INSERT INTO purchase_order_line (id, purchase_order_id, product_id, quantity, delivery_date, notes) VALUES
    (1, 1, 1, 10000, '2026-01-15', NULL),
    (2, 1, 2, 200, '2026-01-15', NULL),
    (3, 1, 3, 300, '2026-01-15', NULL),
    (4, 1, 5, 15000, '2026-01-15', NULL),
    (5, 2, 1, 1, '2026-01-15', NULL),
    (6, 2, 5, 1, '2026-01-15', NULL),
    (7, 3, 1, 1000, '2026-01-15', NULL);

COMMIT;

