"""
Database Schemas for Startup Fundraising Platform

Each Pydantic model represents a MongoDB collection. Collection name is the lowercase
of the class name. Example: User -> "user"
"""

from pydantic import BaseModel, Field, HttpUrl, EmailStr
from typing import List, Optional
from datetime import datetime

class User(BaseModel):
    email: EmailStr = Field(..., description="Email address")
    full_name: Optional[str] = Field(None, description="Full name for investors/admins")
    role: str = Field(..., description="user role: startup | investor | admin")
    company: Optional[str] = Field(None, description="Affiliated company or firm (investor)")
    is_active: bool = Field(True, description="Whether user is active")

class Startuppitch(BaseModel):
    # Collection: startuppitch
    owner_user_id: str = Field(..., description="User id of the startup owner")
    company_name: str = Field(..., description="Startup company name")
    product_description: str = Field(..., description="Rich product description")
    image_urls: List[HttpUrl] = Field(default_factory=list, description="High-res product images/demos")
    previous_funding: Optional[str] = Field(None, description="Details of previous funding rounds")
    status: str = Field("pending", description="listing status: pending | approved | rejected")
    total_raised: float = Field(0.0, ge=0, description="Aggregate total funds successfully raised")

class Investorprofile(BaseModel):
    # Collection: investorprofile
    user_id: str = Field(..., description="Reference to user document")
    full_name: str = Field(..., description="Investor full name")
    company: Optional[str] = Field(None, description="Affiliated company or firm")

class Interest(BaseModel):
    # Collection: interest
    startup_id: str = Field(..., description="Reference to Startuppitch document id")
    investor_user_id: str = Field(..., description="Investor user id")
    message: Optional[str] = Field(None, description="Optional message from investor")
    committed_amount: float = Field(0.0, ge=0, description="Funds investor commits")

class Report(BaseModel):
    # Collection: report
    reporter_user_id: Optional[str] = Field(None, description="User who reported (optional)")
    target_type: str = Field(..., description="What is reported: startup | user | other")
    target_id: Optional[str] = Field(None, description="ID of the target")
    reason: str = Field(..., description="Reason for report")
    status: str = Field("open", description="Report status: open | in_review | resolved")

class Adminaction(BaseModel):
    # Collection: adminaction
    admin_user_id: str = Field(..., description="Admin who performed action")
    action: str = Field(..., description="Action description")
    at: Optional[datetime] = None
