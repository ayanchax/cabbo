from core.security import RoleEnum
from core.trip_helpers import get_default_trip_amenities
from models.financial.payments_enum import PaymentModeEnum
from models.trip.trip_enums import (
    CarTypeEnum,
    FuelTypeEnum,
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
    UniqueConstraint,
   
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
    address=Column(JSON, nullable=True) # We will store the address as a JSON object and validate with Address Schema 
    # e.g., {"address_line1": "123 Main St", "address_line2": "Apt 4B", "region_id": "uuid from regions_master", "state_id": "uuid from states_master", "country_id": "uuid from countries_master", "postal_code": "560001"}
    
    #Cab, fuel details
    cab_type = Column(
        Enum(CarTypeEnum), nullable=False, default=CarTypeEnum.sedan
    )  # sedan, suv, hatchback, etc.
    fuel_type = Column(Enum(FuelTypeEnum), nullable=False, default=FuelTypeEnum.diesel)  # petrol, diesel, electric, hybrid
    cab_model_and_make = Column(String(255), nullable=False) # Cab model and make free text (e.g., Maruti Swift) 
    cab_registration_number = Column(String(32), nullable=False, unique=True) # e.g., KA-01-AB-1234
    cab_amenities= Column(
        JSON, default=get_default_trip_amenities().model_dump(), nullable=True # e.g., {"ac": true, "music_system": true, "wifi": false, "phone_charger": true}
    )  # Cab amenities details

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
        MySQL_CHAR(36), nullable=False, index=True, default=RoleEnum.system.value, comment="ID of the user or system that created this record"
    )  # Created by system, admin, or user
    bearer_token = Column(Text, nullable=True) # Bearer token for authentication, this will be used to authenticate the driver in the driver app when the driver app is released to the drivers.
    # Relationships
    trips = relationship(
        "Trip",
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    ) 
    #A driver can have multiple earnings records for different trips, and each earning record is associated with one trip, so the relationship is one-to-many from Driver to DriverEarning and many-to-one from DriverEarning to Driver.
    earnings = relationship("DriverEarning", back_populates="driver", cascade="all, delete-orphan", passive_deletes=True)
    
    ratings = relationship(
        "DriverRating",
        back_populates="driver",
        cascade="all, delete-orphan",
        passive_deletes=True,
    ) #A driver can have multiple ratings from different customers for different trips, 

#Create a orm for driver earnings per trip id
# This will be populated when the trip is completed and the driver payment is settled from Cabbo's end
class DriverEarning(Base):
    __tablename__ = "driver_earnings"
    __table_args__ = (
    UniqueConstraint("driver_id", "trip_id", name="uq_driver_trip_earning"),
)
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
    earnings = Column(Float, nullable=False)  # total base Earnings for the trip which is the final price minus the platform fee, this is the amount that driver earns for the trip from Cabbo's end, excluding any extra earnings such as tolls paid by driver, parking charges paid by driver, overage payment for extra distance or time beyond what was estimated, tips given to driver by customer for good performance, high ratings, or completing a certain number of trips, etc.
    extra_earnings = Column(Float, nullable=True)  # any extra earnings for the driver on top of the standard fare for the trip, such as tolls paid by driver, parking charges paid by driver, overage payment for extra distance or time beyond what was estimated, tips given to driver by customer for good performance, high ratings, or completing a certain number of trips, etc. 
    extra_earnings_breakdown = Column(
        JSON, nullable=True
    )  # Earnings breakdown details ideally on trip completion e.g., {"toll_charges": 100, "parking_charges": 50, "overage_payment": 30, "tip": 1.5, "total_extra_payment": 270}
    total_earnings = Column(Float, nullable=False)  # total earnings for the driver for the trip including the standard fare and any extra earnings (earnings + extra_earnings)
    # Model validated by ExtraPaymentsToDriverSchema in driver_schema.py to ensure the breakdown is consistent with the total extra payment to driver and the individual components of the extra payment.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by = Column(
        MySQL_CHAR(36), nullable=False, index=True, default=RoleEnum.system.value, comment="ID of the user or system that created this record"
    )  # Created by system, admin, or user
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    is_active = Column(Boolean, default=True, nullable=False)  # Soft delete flag to indicate if the record is active or has been deleted, we will use this to keep the earning record for historical and reporting purposes even if the trip gets deleted or the earning record gets deleted for any reason, we will just set is_active to false instead of deleting the record from the database.

    driver = relationship("Driver", back_populates="earnings")
    trip = relationship("Trip", back_populates="driver_earning")

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
    rating = Column(Float, nullable=False)  # Rating given by the customer out of 5
    feedback = Column(String(500), nullable=True)  # Optional feedback from the customer
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    #rating cannot be updated once set, so no onupdate
    created_by = Column(
        MySQL_CHAR(36), nullable=False, index=True, default=RoleEnum.system.value, comment="ID of the user or system that created this record"
    )  # Created by customer id who gave the rating, this will be used to ensure that the customer can only give one rating per trip and to identify the customer who gave the rating for any follow up if needed.
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    
    driver = relationship("Driver", back_populates="ratings")
    trip = relationship("Trip", back_populates="driver_rating")
    customer = relationship("Customer", back_populates="driver_ratings")
    

