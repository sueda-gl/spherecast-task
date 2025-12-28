"""
SQLAlchemy ORM models for SphereCast Purchase Order system.

These models define the database schema and relationships between tables.
"""

from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


class Product(Base):
    """
    Products in the company's catalog.
    Each product has an internal SKU that the company uses.
    """
    __tablename__ = 'product'
    
    id = Column(Integer, primary_key=True)
    sku = Column(String, nullable=False, unique=True)
    title = Column(String)
    
    supplier_products = relationship("SupplierProduct", back_populates="product")
    purchase_order_lines = relationship("PurchaseOrderLine", back_populates="product")
    
    def __repr__(self):
        return f"<Product(id={self.id}, sku='{self.sku}', title='{self.title}')>"


class Supplier(Base):
    """Suppliers/vendors that provide products to the company."""
    __tablename__ = 'supplier'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String)
    
    supplier_products = relationship("SupplierProduct", back_populates="supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")
    
    def __repr__(self):
        return f"<Supplier(id={self.id}, name='{self.name}')>"


class SupplierProduct(Base):
    """
    The relationship between a supplier and a product.
    
    This is the CRITICAL table for SKU resolution:
    - A supplier may use a DIFFERENT SKU for a product than the internal SKU
    - For example: Internal SKU is "SKU-1-3", but Big Supplier calls it "SKU13"
    """
    __tablename__ = 'supplier_product'
    
    supplier_id = Column(Integer, ForeignKey('supplier.id'), primary_key=True)
    product_id = Column(Integer, ForeignKey('product.id'), primary_key=True)
    supplier_sku = Column(String, nullable=True)
    price_per_unit = Column(Float)
    
    supplier = relationship("Supplier", back_populates="supplier_products")
    product = relationship("Product", back_populates="supplier_products")
    
    def __repr__(self):
        return f"<SupplierProduct(supplier_id={self.supplier_id}, product_id={self.product_id}, supplier_sku='{self.supplier_sku}')>"
    
    def get_effective_sku(self) -> str:
        """Returns the SKU to use - supplier's SKU if set, otherwise internal SKU."""
        return self.supplier_sku if self.supplier_sku else self.product.sku


class PurchaseOrder(Base):
    """
    A purchase order header.
    Contains metadata about the order (supplier, reference numbers, dates).
    """
    __tablename__ = 'purchase_order'
    
    id = Column(Integer, primary_key=True)
    reference_num = Column(String)
    supplier_id = Column(Integer, ForeignKey('supplier.id'), nullable=False)
    delivery_date = Column(Date)
    external_reference = Column(String)
    terms = Column(String)
    notes = Column(Text)
    
    supplier = relationship("Supplier", back_populates="purchase_orders")
    lines = relationship("PurchaseOrderLine", back_populates="purchase_order", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<PurchaseOrder(id={self.id}, reference_num='{self.reference_num}', supplier_id={self.supplier_id})>"


class PurchaseOrderLine(Base):
    """
    Individual line items on a purchase order.
    Each line represents a product, quantity, and expected delivery date.
    """
    __tablename__ = 'purchase_order_line'
    
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey('purchase_order.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('product.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    delivery_date = Column(Date)
    unit_price = Column(Float)
    total_price = Column(Float)
    notes = Column(Text)
    
    purchase_order = relationship("PurchaseOrder", back_populates="lines")
    product = relationship("Product", back_populates="purchase_order_lines")
    
    def __repr__(self):
        return f"<PurchaseOrderLine(id={self.id}, product_id={self.product_id}, quantity={self.quantity})>"


def get_engine(db_path: str = "database/spherecast.db"):
    """Create and return a database engine."""
    return create_engine(f"sqlite:///{db_path}", echo=False)


def create_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    """Create and return a new database session."""
    return Session(engine)

