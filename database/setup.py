"""Database setup script using SQLAlchemy ORM."""

from datetime import date
from pathlib import Path

from models import (
    Base, Product, Supplier, SupplierProduct, 
    PurchaseOrder, PurchaseOrderLine,
    get_engine, create_tables, get_session
)

DB_PATH = Path(__file__).parent / "spherecast.db"


def seed_data(session):
    """Insert initial data from the Google Sheets."""
    products = [
        Product(id=1, sku="SKU-1", title="PRODUCT ONE | GLOBAL VERSION"),
        Product(id=2, sku="SKU-2", title="PRODUCT TWO with Vitamin A, B, C"),
        Product(id=3, sku="SKU-3", title="-"),
        Product(id=4, sku="SKU-4", title="(Test) Internal test for v2 of SKU-2"),
        Product(id=5, sku="SKU-1-3", title="PRODUCT ONE | GLOBAL VERSION updated v3"),
    ]
    session.add_all(products)
    
    suppliers = [
        Supplier(id=1, name="Big Supplier", email="big@supplier.com"),
        Supplier(id=2, name="Small Supplier", email="small@supplier.com"),
    ]
    session.add_all(suppliers)
    session.commit()
    
    supplier_products = [
        SupplierProduct(supplier_id=1, product_id=1, supplier_sku=None, price_per_unit=1),
        SupplierProduct(supplier_id=1, product_id=2, supplier_sku=None, price_per_unit=1),
        SupplierProduct(supplier_id=1, product_id=3, supplier_sku=None, price_per_unit=1),
        SupplierProduct(supplier_id=1, product_id=5, supplier_sku="SKU13", price_per_unit=2),
        SupplierProduct(supplier_id=2, product_id=1, supplier_sku=None, price_per_unit=1),
    ]
    session.add_all(supplier_products)
    
    purchase_orders = [
        PurchaseOrder(id=1, reference_num="PO-12", supplier_id=1, delivery_date=date(2026, 1, 15)),
        PurchaseOrder(id=2, reference_num="PO-22", supplier_id=1, delivery_date=date(2026, 1, 15)),
        PurchaseOrder(id=3, reference_num="PO-35", supplier_id=2, delivery_date=date(2026, 1, 15)),
    ]
    session.add_all(purchase_orders)
    session.commit()
    
    po_lines = [
        PurchaseOrderLine(id=1, purchase_order_id=1, product_id=1, quantity=10000, delivery_date=date(2026, 1, 15)),
        PurchaseOrderLine(id=2, purchase_order_id=1, product_id=2, quantity=200, delivery_date=date(2026, 1, 15)),
        PurchaseOrderLine(id=3, purchase_order_id=1, product_id=3, quantity=300, delivery_date=date(2026, 1, 15)),
        PurchaseOrderLine(id=4, purchase_order_id=1, product_id=5, quantity=15000, delivery_date=date(2026, 1, 15)),
        PurchaseOrderLine(id=5, purchase_order_id=2, product_id=1, quantity=1, delivery_date=date(2026, 1, 15)),
        PurchaseOrderLine(id=6, purchase_order_id=2, product_id=5, quantity=1, delivery_date=date(2026, 1, 15)),
        PurchaseOrderLine(id=7, purchase_order_id=3, product_id=1, quantity=1000, delivery_date=date(2026, 1, 15)),
    ]
    session.add_all(po_lines)
    session.commit()


def create_database():
    """Create the database with schema and seed data."""
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    engine = get_engine(str(DB_PATH))
    create_tables(engine)
    
    session = get_session(engine)
    seed_data(session)
    session.close()
    
    print(f"Database created: {DB_PATH}")
    return DB_PATH


if __name__ == "__main__":
    create_database()

