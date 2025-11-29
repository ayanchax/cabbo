from core.security import RoleEnum
from models.financial.payments_enum import PaymentModeEnum
from models.trip.trip_enums import (
    CarTypeEnum,
)
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    String,
    Enum,
    Float,
    DateTime,
    Boolean,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
from models.user.user_enum import GenderEnum, NationalityEnum, ReligionEnum


class Driver(Base):
    __tablename__ = "drivers"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    phone = Column(String(32), nullable=False, unique=True) #When driver app is opened for drivers, we will use this as the primary phone number for OTP authentication as they login, just like we do for customers.
    email = Column(String(255), nullable=True, unique=True)
    #Secondary data
    gender = Column(Enum(GenderEnum, name="gender_enum"), nullable=False, default=GenderEnum.male)
    dob = Column(DateTime, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_number = Column(String(20), nullable=True)
    #We are keeping the nationality and religion optional for now, we will use this information for KYC verification when we open the app for drivers
    nationality = Column(Enum(NationalityEnum), nullable=True, default=NationalityEnum.indian)  # e.g., Indian, American
    religion = Column(Enum(ReligionEnum), nullable=True)  # e.g., Hindu, Muslim, Christian
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    country_id = Column(String(100), ForeignKey("countries_master.id"), nullable=True)
    region_id = Column(String(100), ForeignKey("regions_master.id"), nullable=True) #We will link this to the regions_master aka city table to know which region the driver is operating in
    state_id = Column(String(100), ForeignKey("states_master.id"), nullable=True)
    postal_code = Column(String(20), nullable=True)
    #Car details
    car_type = Column(
        Enum(CarTypeEnum), nullable=False, default=CarTypeEnum.sedan
    )  # sedan, suv, hatchback, etc.
    car_model = Column(String(255), nullable=False) # Car model (e.g., Maruti Swift)
    car_registration_number = Column(String(32), nullable=False, unique=True) # e.g., KA-01-AB-1234
    
    #Payment intake details
    payment_mode = Column(Enum(PaymentModeEnum), nullable=False)  # gpay, phonepe, paytm
    payment_phone_number = Column(String(32), nullable=True)  # Alternate payment phone number for upi payments like gpay, phonepe, paytm, if not provided, use phone number
    bank_details= Column(
        JSON, nullable=True
    )  # Bank details for bank transfer payments e.g., account name, account number, IFSC code
    
    #We will use this for KYC verification when we open the app for drivers
    kyc_documents = Column(
        JSON, nullable=True #[{"document_type": "driver_license", "document_url": "/documents/drivers/{driver_id_directory}/driver_license.jpg", "verified": True, "extension":".jpg", "size":111}...]
    )  # KYC document details e.g., Driver license, Pollution certificate, insurance, Aadhar card, PAN card, etc.
    kyc_verified = Column(
        Boolean, default=False, nullable=False
    )  # KYC verification status will be set to true when the driver uploads the required KYC documents and they are all verified by the admin
    
    #Rating count: We will use this to calculate the average rating of the driver based on customer ratings, we will make this available in the driver app
    avg_rating = Column(Float, nullable=True)  # Driver rating
   
    #we will use this to track the driver availability status when we implement the driver app
    is_available = Column(Boolean, default=True, nullable=False)  # Driver availability status
    
    is_active = Column(Boolean, default=True, nullable=False)  # Active status
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    created_by = Column(
        Enum(RoleEnum), nullable=False, default=RoleEnum.driver_admin
    )  # Created by system, admin, or user
    bearer_token = Column(Text, nullable=True) # Bearer token for authentication, this will be used to authenticate the driver in the driver app when the driver app is released to the drivers.
    # Relationships
    trips = relationship(
        "Trip",
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    ) 
    earnings = relationship("DriverEarnings", back_populates="driver", cascade="all, delete-orphan", passive_deletes=True)
    ratings = relationship(
        "DriverRating",
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

#Create a orm for driver earnings per trip id
# This will be populated when the trip is completed and the driver payment is settled from Cabbo's end
class DriverEarnings(Base):
    __tablename__ = "driver_earnings"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    driver_id = Column(
        MySQL_CHAR(36), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False
    )
    trip_id = Column(
        MySQL_CHAR(36), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    earnings = Column(Float, nullable=False)  # Earnings for the trip
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by = Column(
        Enum(RoleEnum), nullable=False, default=RoleEnum.finance_admin
    )  # Created by system, admin, or user
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    driver = relationship("Driver", back_populates="earnings")
    trip = relationship("Trip", back_populates="driver_earnings")

#Create a orm for the driver ratings per customer per trip
#This will be populated when the customer rates the driver after the trip is completed
class DriverRating(Base):
    __tablename__ = "driver_ratings"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    driver_id = Column(
        MySQL_CHAR(36), ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False
    )
    trip_id = Column(
        MySQL_CHAR(36), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    customer_id = Column(
        MySQL_CHAR(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    rating = Column(Float, nullable=False)  # Rating given by the customer
    feedback = Column(String(500), nullable=True)  # Optional feedback from the customer
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    #rating cannot be updated once set, so no onupdate
    created_by = Column(
        Enum(RoleEnum), nullable=False, default=RoleEnum.customer
    )  # Created by customer
    
    driver = relationship("Driver", back_populates="ratings")
    trip = relationship("Trip", back_populates="driver_ratings")
    customer = relationship("Customer", back_populates="driver_ratings")
    

