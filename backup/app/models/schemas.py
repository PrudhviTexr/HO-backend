from pydantic import BaseModel, EmailStr
from pydantic import ConfigDict
from typing import Optional, List, Dict, Any
import datetime as dt

class DocumentUpload(BaseModel):
    name: str
    url: str
    type: str = "other"
    file_type: str = "application/pdf"
    file_size: int = 0

class SignupRequest(BaseModel):
    model_config = ConfigDict(extra='allow')  # Allow extra fields for location data and agent-specific fields
    email: EmailStr
    password: str
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = "buyer"
    phone_number: str | None = None
    city: str | None = None
    state: str | None = None
    # Location fields (important for agents - zipcode enables property assignment matching)
    zip_code: str | None = None
    district: str | None = None
    mandal: str | None = None
    address: str | None = None
    latitude: str | float | None = None
    longitude: str | float | None = None
    # Agent-specific fields
    experience_years: str | None = None
    specialization: str | None = None
    # Legacy support
    documents: List[DocumentUpload] | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class EmailRequest(BaseModel):
    to: EmailStr
    subject: str
    html: str

class SendOTPRequest(BaseModel):
    email: str  # Changed from phone to email
    action: str = "email_verification"  # Changed default action

class VerifyOTPRequest(BaseModel):
    email: str  # Changed from phone to email
    otp: str
    action: str = "email_verification"

class BankDetailsRequest(BaseModel):
    bank_account_number: str
    ifsc_code: str
    otp: str
    phone: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    otp: str
    phone: str

class UpdateProfileRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    city: str | None = None
    state: str | None = None
    district: str | None = None
    mandal: str | None = None
    zip_code: str | None = None
    address: str | None = None
    latitude: str | float | None = None
    longitude: str | float | None = None
    bio: str | None = None
    date_of_birth: str | None = None
    profile_image_url: str | None = None
    business_name: str | None = None
    otp: str | None = None
    current_password: str | None = None  # For password validation when updating sensitive fields
    status: str | None = None  # For admin user management
    verification_status: str | None = None  # For admin user management
    admin_notes: str | None = None  # For admin user management

class PropertyRequest(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: str
    description: str
    price: float | None = None
    monthly_rent: float | None = None
    security_deposit: float | None = None
    property_type: str
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqft: float
    address: str
    # Make city/state optional to accept frontend payloads that send *_id fields
    city: str | None = None
    state: str | None = None
    # Frontend may send identifiers for geo hierarchy instead of names
    state_id: str | None = None
    district_id: str | None = None
    mandal_id: str | None = None
    zip_code: str
    latitude: float | None = None
    longitude: float | None = None
    listing_type: str
    furnishing_status: str | None = None
    available_from: str | None = None
    amenities: List[str] = []
    images: List[str] = []

class InquiryRequest(BaseModel):
    property_id: str
    name: str
    email: EmailStr
    phone: str | None = None
    message: str
    inquiry_type: str = "general"

class BookingRequest(BaseModel):
    property_id: str
    name: str
    email: EmailStr
    phone: str | None = None
    booking_date: str
    booking_time: str
    notes: str | None = None

class BookingUpdateRequest(BaseModel):
    agent_id: Optional[str] = None
    status: str
    agent_notes: str | None = None
    booking_date: str | None = None
    booking_time: str | None = None

class InquiryUpdateRequest(BaseModel):
    status: str
    agent_notes: str | None = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    otp: str
    phone: str