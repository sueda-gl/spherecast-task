"""
SQLAlchemy ORM models for SphereCast Purchase Order system.

These models define the database schema and relationships between tables.
"""

from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


class Product(Base):

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
  
    __tablename__ = 'purchase_order_line'
    
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey('purchase_order.id'), nullable=False)
    product_id = Column(Integer, ForeignKey('product.id'), nullable=False)
    quantity = Column(Integer, nullable=False)
    delivery_date = Column(Date)
    notes = Column(Text)
    
    purchase_order = relationship("PurchaseOrder", back_populates="lines")
    product = relationship("Product", back_populates="purchase_order_lines")
    
    def __repr__(self):
        return f"<PurchaseOrderLine(id={self.id}, product_id={self.product_id}, quantity={self.quantity})>"


def get_engine(db_path: str = "database/spherecast.db"):
    """Create and return a database engine.
    
    Configured with:
    - WAL mode: Allows concurrent reads during writes (critical for background processing)
    - Timeout: 30 second timeout to avoid indefinite blocking
    - check_same_thread=False: Required for multi-threaded access (FastAPI background tasks)
    """
    from sqlalchemy import event
    
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={
            "check_same_thread": False,  # Allow multi-threaded access
            "timeout": 30  # 30 second timeout for lock acquisition
        },
        pool_pre_ping=True,  # Verify connections are still valid
        pool_recycle=3600,  # Recycle connections after 1 hour
    )
    
    # Enable WAL mode for concurrent reads during writes
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # Good balance of safety and speed
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        cursor.close()
    
    return engine


def create_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    """Create and return a new database session."""
    return Session(engine)

