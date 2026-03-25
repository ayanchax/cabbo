# Service Type: CONFIGURATION | Unique Constraints: "trip_type_id","region_id","package_label",
# Target table: TripPackageConfig | trip_package_config
# Service functions for trip package configuration management for local/hourly trip packages in the system configuration. These functions will be called by the API endpoints for local trip package management.
from core.exceptions import CabboException
from core.store import ConfigStore
from models.geography.region_orm import RegionModel
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import TripPackageConfig
from models.trip.trip_schema import TripPackageSchema, TripPackageUpdateSchema
from sqlalchemy.ext.asyncio import AsyncSession
from services.geography_service import async_get_region_by_code
from services.trip_type_service import async_get_trip_type_by_name
from sqlalchemy import select
_TRIP_PACKAGE_SCHEMA_FIELDS = TripPackageSchema.model_fields.keys()

async def create_trip_package_config(
    payload: TripPackageSchema, db: AsyncSession, requestor: str
):
    try:
        if payload.included_km <= 0:
            raise CabboException(
                "Included kilometers must be greater than zero", status_code=400
            )
        if payload.included_hours <= 0:
            raise CabboException(
                "Included hours must be greater than zero", status_code=400
            )
        if payload.included_hours >= 12:
            if payload.driver_allowance is None or payload.driver_allowance <= 0:
                raise CabboException(
                    "Driver allowance must be provided and greater than zero for packages with included hours greater than or equal to 12",
                    status_code=400,
                )

        region_code = payload.region_code
        if not region_code:
            raise CabboException(
                "Region code is required for creating a trip package configuration",
                status_code=400,
            )
        region = await async_get_region_by_code(region_code, db)
        if not region:
            raise CabboException(
                f"Region with code {region_code} does not exist", status_code=404
            )
        region_id = region.id
        trip_type = payload.trip_type if payload.trip_type else TripTypeEnum.local
        trip_type = await async_get_trip_type_by_name(
            trip_type, db
        )  # Validate that the trip type exists
        if not trip_type:
            raise CabboException(f"Trip type does not exist", status_code=404)

        trip_type_id = trip_type.id

        package_label = f"{payload.included_hours}Hours / {payload.included_km:g}KM"

        new_trip_package_config = TripPackageConfig(
            region_id=region_id,
            trip_type_id=trip_type_id,
            included_hours=payload.included_hours,
            included_km=payload.included_km,
            driver_allowance=payload.driver_allowance,
            package_label=package_label,
            created_by=requestor,
        )
        db.add(new_trip_package_config)
        await db.commit()
        await db.refresh(new_trip_package_config)
        ConfigStore.reset_instance()  # Reset the config store instance to refresh the cache
        

        return TripPackageSchema.model_validate(
            {
                **{
                    c.key: getattr(new_trip_package_config, c.key)
                    for c in TripPackageConfig.__table__.columns
                    if c.key in _TRIP_PACKAGE_SCHEMA_FIELDS
                },
                "region_code": region_code,
            }
        )
        
    except CabboException as ce:
        await db.rollback()
        raise ce
    except Exception as e:
        await db.rollback()
        raise CabboException(str(e), status_code=500)


async def list_trip_package_configs(db: AsyncSession):
    try:
        stmt = select(TripPackageConfig, RegionModel.region_code).join(
            RegionModel, TripPackageConfig.region_id == RegionModel.id
        )
        stmt = stmt.filter(TripPackageConfig.is_active == True)
        result = await db.execute(stmt)
        rows = result.all()
        return [
            TripPackageSchema.model_validate(
                {
                    **{
                        c.key: getattr(config, c.key)
                        for c in TripPackageConfig.__table__.columns
                        if c.key in _TRIP_PACKAGE_SCHEMA_FIELDS
                    },
                    "region_code": region_code,
                }
            )
            for config, region_code in rows
        ]
    except Exception as e:
        raise CabboException(str(e), status_code=500)


async def get_trip_package_config_by_id(id: str, db: AsyncSession):
    try:
        stmt = select(TripPackageConfig, RegionModel.region_code).join(
            RegionModel, TripPackageConfig.region_id == RegionModel.id
        )
        stmt = stmt.where(
            TripPackageConfig.id == id, TripPackageConfig.is_active == True
        )
        result = await db.execute(stmt)
        row = result.one_or_none()
        if not row:
            raise CabboException(
                f"Trip package config with id {id} does not exist", status_code=404
            )
        config, region_code = row
        return TripPackageSchema.model_validate(
            {
                **{
                    c.key: getattr(config, c.key)
                    for c in TripPackageConfig.__table__.columns
                    if c.key in _TRIP_PACKAGE_SCHEMA_FIELDS
                },
                "region_code": region_code,
            }
        )
    except Exception as e:
        raise CabboException(str(e), status_code=500)


async def update_trip_package_config(
    payload: TripPackageUpdateSchema, db: AsyncSession
):
    try:

        if payload.id is None or payload.id.strip() == "":
            raise CabboException(
                "Trip package config ID is required for update", status_code=400
            )
        if payload.included_km is not None and payload.included_km <= 0:
            raise CabboException(
                "Included kilometers must be greater than zero", status_code=400
            )
        if payload.included_hours is not None and payload.included_hours <= 0:
            raise CabboException(
                "Included hours must be greater than zero", status_code=400
            )
        if payload.included_hours >= 12:
            if payload.driver_allowance is None or payload.driver_allowance <= 0:
                raise CabboException(
                    "Driver allowance must be provided and greater than zero for packages with included hours greater than or equal to 12",
                    status_code=400,
                )
        stmt = (
            select(TripPackageConfig, RegionModel.region_code)
            .join(RegionModel, TripPackageConfig.region_id == RegionModel.id)
            .where(
                TripPackageConfig.id == payload.id, TripPackageConfig.is_active == True
            )
        )
        result = await db.execute(stmt)
        row = result.one_or_none()
        if not row:
            raise CabboException(
                f"Trip package config with id {payload.id} does not exist",
                status_code=404,
            )

        trip_package_config: TripPackageConfig
        region_code: str
        trip_package_config, region_code = row
        trip_package_config.included_hours = (
            payload.included_hours or trip_package_config.included_hours
        )
        trip_package_config.included_km = (
            payload.included_km or trip_package_config.included_km
        )
        trip_package_config.driver_allowance = (
            payload.driver_allowance or trip_package_config.driver_allowance
        )
        trip_package_config.package_label = f"{trip_package_config.included_hours}Hours / {trip_package_config.included_km:g}KM"

        await db.commit()
        await db.refresh(trip_package_config)
        ConfigStore.reset_instance()  # Reset the config store instance to refresh the cache
        return TripPackageSchema.model_validate(
            {
                **{
                    c.key: getattr(trip_package_config, c.key)
                    for c in TripPackageConfig.__table__.columns
                    if c.key in _TRIP_PACKAGE_SCHEMA_FIELDS
                },
                "region_code": region_code,
            }
        )
    except Exception as e:
        await db.rollback()
        raise CabboException(str(e), status_code=500)


async def delete_trip_package_config_by_id(id: str, db: AsyncSession):
    try:
        stmt = select(TripPackageConfig).where(
            TripPackageConfig.id == id, TripPackageConfig.is_active == True
        )
        result = await db.execute(stmt)
        trip_package_config = result.scalar_one_or_none()
        if not trip_package_config:
            raise CabboException(
                f"Trip package config with id {id} does not exist", status_code=404
            )
        trip_package_config.is_active = False
        await db.commit()
        await db.refresh(trip_package_config)
        ConfigStore.reset_instance()  # Reset the config store instance to refresh the cache
        return True
    except Exception as e:
        await db.rollback()
        raise CabboException(str(e), status_code=500)


async def list_trip_package_configs_by_region_code(region_code: str, db: AsyncSession):
    try:
        region = await async_get_region_by_code(region_code, db)
        if not region:
            raise CabboException(
                f"Region with code {region_code} does not exist", status_code=404
            )
        region_id = region.id
        if not region_id:
            raise CabboException(
                f"Region with code {region_code} does not have a valid ID",
                status_code=404,
            )

        stmt = select(TripPackageConfig).where(
            TripPackageConfig.region_id == region_id,
            TripPackageConfig.is_active == True,
        )
        result = await db.execute(stmt)
        trip_package_configs = result.scalars().all()
        return [
            TripPackageSchema.model_validate(
                {
                    **{
                        c.key: getattr(config, c.key)
                        for c in TripPackageConfig.__table__.columns
                        if c.key in _TRIP_PACKAGE_SCHEMA_FIELDS
                    },
                    "region_code": region_code,
                }
            )
            for config in trip_package_configs
        ]
    except CabboException as ce:
        raise ce
    except Exception as e:
        raise CabboException(str(e), status_code=500)


async def activate_trip_package_config_by_id(id: str, db: AsyncSession):
    try:
        stmt = select(TripPackageConfig).where(
            TripPackageConfig.id == id
        )
        result = await db.execute(stmt)
        trip_package_config = result.scalar_one_or_none()
        if not trip_package_config:
            raise CabboException(
                f"Trip package config with id {id} does not exist",
                status_code=404,
            )
        if trip_package_config.is_active:
            raise CabboException(
                f"Trip package config with id {id} is already active",
                status_code=400,
            )
        trip_package_config.is_active = True
        await db.commit()
        await db.refresh(trip_package_config)
        ConfigStore.reset_instance()  # Reset the config store instance to refresh the cache
        return True
    except Exception as e:
        await db.rollback()
        raise CabboException(str(e), status_code=500)
