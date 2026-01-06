from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Integer, Float, UniqueConstraint
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_type: Mapped[str] = mapped_column(String(32), default="buyer")  # Primary role
    status: Mapped[str] = mapped_column(String(32), default="active")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Bank & agent licensing fields
    bank_account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ifsc_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    account_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    agent_license_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class UserRole(Base):
    __tablename__ = "user_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # buyer, seller, agent, admin
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, pending, suspended
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Ensure unique user-role combinations
    __table_args__ = (
        UniqueConstraint('user_id', 'role', name='unique_user_role'),
    )


class EmailToken(Base):
    __tablename__ = "email_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32))  # verify | reset
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    added_by_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    
    # Extended fields for richer listing data (align with frontend AddPropertyModal)
    monthly_rent: Mapped[float | None] = mapped_column(Float, nullable=True)
    security_deposit: Mapped[float | None] = mapped_column(Float, nullable=True)
    maintenance_charges: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_per_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    rate_per_sqyd: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Pricing display fields for new property types (new_property, lot)
    pricing_display_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 'starting_from', 'per_unit', 'fixed'
    starting_price_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)  # Starting price per sqft/sqyd
    pricing_unit_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'sqft' or 'sqyd'
    
    property_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balconies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Area measurements
    area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_sqyd: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_acres: Mapped[float | None] = mapped_column(Float, nullable=True)
    carpet_area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    built_up_area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    plot_area_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    plot_area_sqyd: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Commercial property fields
    commercial_subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parking_spaces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Villa/house specific fields
    bhk_config: Mapped[str | None] = mapped_column(String(20), nullable=True)
    floor_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    facing: Mapped[str | None] = mapped_column(String(20), nullable=True)
    private_garden: Mapped[bool] = mapped_column(Boolean, default=False)
    private_driveway: Mapped[bool] = mapped_column(Boolean, default=False)
    plot_dimensions: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Land/farm specific fields
    land_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    soil_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    road_access: Mapped[bool] = mapped_column(Boolean, default=True)
    boundary_fencing: Mapped[bool] = mapped_column(Boolean, default=False)
    water_availability: Mapped[bool] = mapped_column(Boolean, default=False)
    electricity_availability: Mapped[bool] = mapped_column(Boolean, default=False)
    corner_plot: Mapped[bool] = mapped_column(Boolean, default=False)
    water_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Apartment specific fields
    apartment_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    
    # Community and legal fields
    community_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gated_community_features: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array as text
    visitor_parking: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rera_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rera_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Media and business context fields
    nearby_business_hubs: Mapped[str | None] = mapped_column(Text, nullable=True)
    nearby_transport: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Location fields
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mandal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    district_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mandal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Ownership and management fields
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Status and visibility fields
    status: Mapped[str] = mapped_column(String(32), default="active")
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    
    # Listing details
    listing_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    available_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    furnishing_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    possession_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # JSON fields
    amenities_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array as text
    images_json: Mapped[str | None] = mapped_column(Text, nullable=True)     # JSON array of URLs/IDs
    
    # Note: cover_photo_url is no longer stored in properties table
    # It is fetched from documents table where document_category='cover_photo'
    # The backend adds it to property responses dynamically
    
    # Custom ID
    custom_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Inquiry(Base):
    __tablename__ = "inquiries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_time: Mapped[str | None] = mapped_column(String(120), nullable=True)
    booking_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    booking_time: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | confirmed | cancelled | completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50))  # user | property | booking | inquiry
    entity_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class PropertyViewing(Base):
    __tablename__ = "property_viewings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentReview(Base):
    __tablename__ = "agent_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id", ondelete="SET NULL"), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class OTPToken(Base):
    __tablename__ = "otp_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(64), index=True)
    token: Mapped[str] = mapped_column(String(16), index=True)
    purpose: Mapped[str] = mapped_column(String(32))  # login | verify
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
