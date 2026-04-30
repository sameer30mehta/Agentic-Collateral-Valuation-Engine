from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, ForeignKey, Text, Index, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid

Base = declarative_base()

class Property(Base):
    """Main property record"""
    __tablename__ = "properties"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    address = Column(String(500), nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    property_type = Column(String(50), nullable=False)  # apartment, house, etc
    config = Column(String(50), nullable=True)  # 2BHK, 3BHK, etc
    carpet_area = Column(Float, nullable=False)
    age_bucket = Column(String(50), nullable=True)  # pre-1990, 1990-2005, etc
    pincode = Column(String(10), nullable=False, index=True)
    city = Column(String(100), nullable=False, index=True)
    
    # Status
    status = Column(String(50), default="draft")  # draft, submitted, verified, approved, rejected
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    valuations = relationship("Valuation", back_populates="property", cascade="all, delete-orphan")
    fraud_checks = relationship("FraudCheck", back_populates="property", cascade="all, delete-orphan")
    images = relationship("PropertyImage", back_populates="property", cascade="all, delete-orphan")

class Valuation(Base):
    """Valuation result"""
    __tablename__ = "valuations"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id = Column(String(36), ForeignKey("properties.id"), nullable=False, index=True)
    
    # Valuation outputs
    market_value = Column(String(50), nullable=False)  # e.g., "₹2.5 Cr - ₹3.2 Cr"
    distress_value = Column(String(50), nullable=False)
    propScore = Column(Float, nullable=True)  # 0-100
    confidence_score = Column(Float, nullable=False)  # 0-1
    confidence_breakdown = Column(JSON, nullable=True)  # base, legal, visual, historical
    
    # Supporting data
    circle_rate = Column(Float, nullable=True)
    market_multiplier = Column(Float, nullable=True)  # XGBoost output
    liquidity_discount = Column(Float, nullable=True)
    time_to_sell = Column(String(100), nullable=True)
    
    # Metadata
    pipeline_execution_time = Column(Float, nullable=True)
    has_images = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Raw outputs
    raw_output = Column(JSON, nullable=True)
    
    property = relationship("Property", back_populates="valuations")

class FraudCheck(Base):
    """Fraud detection results"""
    __tablename__ = "fraud_checks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id = Column(String(36), ForeignKey("properties.id"), nullable=False, index=True)
    valuation_id = Column(String(36), ForeignKey("valuations.id"), nullable=True)
    
    # Fraud layers
    phash_match = Column(Boolean, default=False)
    phash_score = Column(Float, nullable=True)
    
    clip_similarity = Column(Float, nullable=True)
    clip_flag = Column(Boolean, default=False)
    
    listing_photo_detected = Column(Boolean, default=False)
    
    size_sanity_pass = Column(Boolean, default=True)
    size_sanity_message = Column(String(500), nullable=True)
    
    location_consistency_score = Column(Float, nullable=True)
    location_consistency_flag = Column(Boolean, default=False)
    
    # Overall
    risk_level = Column(String(50), default="low")  # low, medium, high, critical
    all_flags = Column(JSON, nullable=True)  # Array of flag details
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    property = relationship("Property", back_populates="fraud_checks")

class PropertyImage(Base):
    """Property images"""
    __tablename__ = "property_images"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id = Column(String(36), ForeignKey("properties.id"), nullable=False, index=True)
    
    image_type = Column(String(50), nullable=False)  # exterior, interior_living, interior_kitchen, site_plan
    image_url = Column(Text, nullable=False)
    image_hash = Column(String(100), nullable=True)  # pHash for duplicate detection
    image_embedding = Column(Text, nullable=True)  # CLIP embedding (stored as JSON string)
    
    # VLM Analysis results
    vision_analysis = Column(JSON, nullable=True)  # condition_score, defects, materials, etc
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    property = relationship("Property", back_populates="images")

class CircleRate(Base):
    """Government circle rates (property floor values)"""
    __tablename__ = "circle_rates"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pincode = Column(String(10), nullable=False, index=True)
    property_type = Column(String(50), nullable=False)  # apartment, house, etc
    rate_per_sqft = Column(Float, nullable=False)
    city = Column(String(100), nullable=False, index=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    source = Column(String(100), nullable=True)  # IGRS, manual, etc
    
    __table_args__ = (
        Index('idx_pincode_type_city', 'pincode', 'property_type', 'city'),
    )

class ListingStats(Base):
    """Aggregated market data from scraped listings"""
    __tablename__ = "listing_stats"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pincode = Column(String(10), nullable=False, index=True)
    config = Column(String(50), nullable=False)  # 2BHK, 3BHK, etc
    
    # Statistics
    median_price_per_sqft = Column(Float, nullable=True)
    p25_price_per_sqft = Column(Float, nullable=True)
    p75_price_per_sqft = Column(Float, nullable=True)
    
    median_area = Column(Float, nullable=True)
    listing_count = Column(Integer, nullable=True)
    median_days_listed = Column(Float, nullable=True)
    
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_pincode_config', 'pincode', 'config'),
    )

class IPICache(Base):
    """Pre-computed IPI (Infrastructure Proximity Index) grid"""
    __tablename__ = "ipi_cache"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    grid_point_id = Column(String(100), nullable=False, unique=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    
    metro_distance_m = Column(Float, nullable=True)
    highway_distance_m = Column(Float, nullable=True)
    commercial_hub_distance_m = Column(Float, nullable=True)
    school_distance_m = Column(Float, nullable=True)
    hospital_distance_m = Column(Float, nullable=True)
    
    ipi_score = Column(Float, nullable=True)  # Composite score 0-100
    
    computed_at = Column(DateTime, default=datetime.utcnow)

from config import settings

def get_db_engine(database_url: str):
    """Create database engine with DB-specific options."""
    # SQLite requires a special connect_args and does not accept pool_size/max_overflow
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )

    # Default (Postgres etc.)
    return create_engine(
        database_url,
        echo=False,
        pool_size=20,
        max_overflow=40,
    )

def get_db_session(engine):
    """Create session factory"""
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

engine = get_db_engine(settings.DATABASE_URL)
SessionLocal = get_db_session(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
