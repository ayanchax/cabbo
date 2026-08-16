import logging
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from core.exceptions import CabboException, GENERIC_EXCEPTION
from core.security import RoleEnum
from models.geography.country_orm import CountryModel
from models.geography.region_orm import RegionModel
from models.geography.state_orm import StateModel
from models.map.location_schema import LocationInfo
from models.support.support_enum import SupportScopeEnum, SupportTypeEnum
from models.support.support_orm import SupportContact, SupportRoutingRule
from models.support.support_schema import (
    SupportContactCreate,
    SupportContactListSchema,
    SupportContactSchema,
    SupportContactUpdate,
    SupportRoutingRuleCreate,
    SupportRoutingRuleSchema,
    SupportRoutingRuleUpdate,
    TripTypeScope,
)
from models.trip.trip_enums import TripTypeEnum
from services.geography_service import async_get_country_by_code, async_get_region_by_code, async_get_state_by_state_code
from core.config import settings
log = logging.getLogger(__name__)

CUSTOMER_SUPPORT_REGION_TRIP_TYPE_SCOPES = [
    TripTypeEnum.local.value,
    TripTypeEnum.airport_pickup.value,
    TripTypeEnum.airport_drop.value,
]

CUSTOMER_SUPPORT_STATE_TRIP_TYPE_SCOPES = [
    TripTypeEnum.outstation.value,
]


async def create_support_contact(
    payload: SupportContactCreate,
    db: AsyncSession,
    requestor: str,
) -> SupportContactSchema:
    try:
        contact = SupportContact(
            display_name=payload.display_name,
            email=str(payload.email),
            phone_number=payload.phone_number,
            whatsapp_number=payload.whatsapp_number,
            support_type=payload.support_type,
            is_active=payload.is_active,
            created_by=requestor,
        )
        db.add(contact)
        await db.flush()

        if payload.routing_rules:
            for rule_payload in payload.routing_rules:
                await _create_routing_rule_model(
                    support_contact_id=contact.id,
                    payload=rule_payload,
                    db=db,
                    requestor=requestor,
                )

        await db.commit()
        return await get_support_contact_by_id(contact.id, db, include_inactive=True)
    except CabboException:
        await db.rollback()
        raise
    except IntegrityError as e:
        await db.rollback()
        log.error(f"Support contact integrity error: {str(e)}")
        raise CabboException(
            "A support contact or routing rule with these details already exists.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    except Exception as e:
        await db.rollback()
        log.error(f"Error creating support contact: {str(e)}")
        raise CabboException(
            f"Failed to create support contact: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


def seed_customer_support_contact_for_serviceable_geographies(
    db: Session,
    email: str,
    phone_number: str,
    display_name: str = "Cabbo Customer Support",
    whatsapp_number: Optional[str] = None,
    created_by: str = RoleEnum.system.value,
) -> SupportContact:
    contact = _get_or_create_seed_support_contact(
        db=db,
        display_name=display_name,
        email=email,
        phone_number=phone_number,
        whatsapp_number=whatsapp_number,
        created_by=created_by,
        support_type=SupportTypeEnum.customer,
    )

    countries = db.query(CountryModel).filter(CountryModel.is_serviceable == True).all()
    states = db.query(StateModel).filter(StateModel.is_serviceable == True).all()
    regions = db.query(RegionModel).filter(RegionModel.is_serviceable == True).all()

    for country in countries:
        _get_or_create_seed_routing_rule(
            db=db,
            contact=contact,
            scope_type=SupportScopeEnum.country,
            scope_id=country.id,
            trip_type_scope="all",
            created_by=created_by,
        )

    for state in states:
        for trip_type_scope in CUSTOMER_SUPPORT_STATE_TRIP_TYPE_SCOPES:
            _get_or_create_seed_routing_rule(
                db=db,
                contact=contact,
                scope_type=SupportScopeEnum.state,
                scope_id=state.id,
                trip_type_scope=trip_type_scope,
                created_by=created_by,
            )

    for region in regions:
        for trip_type_scope in CUSTOMER_SUPPORT_REGION_TRIP_TYPE_SCOPES:
            _get_or_create_seed_routing_rule(
                db=db,
                contact=contact,
                scope_type=SupportScopeEnum.region,
                scope_id=region.id,
                trip_type_scope=trip_type_scope,
                created_by=created_by,
            )

    db.flush()
    return contact


async def get_support_contact_by_id(
    contact_id: str,
    db: AsyncSession,
    include_inactive: bool = False,
) -> SupportContactSchema:
    contact = await _get_support_contact_model(
        contact_id=contact_id,
        db=db,
        include_inactive=include_inactive,
    )
    return SupportContactSchema.model_validate(contact)


async def list_support_contacts(
    db: AsyncSession,
    support_type: Optional[SupportTypeEnum] = None,
    scope_type: Optional[SupportScopeEnum] = None,
    scope_id: Optional[str] = None,
    trip_type_scope: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> SupportContactListSchema:
    page = max(page, 1)
    limit = max(limit, 1)
    offset = (page - 1) * limit

    filters = []
    if is_active is not None:
        filters.append(SupportContact.is_active == is_active)
    if support_type:
        filters.append(SupportContact.support_type == support_type)
    if search:
        search_pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                SupportContact.display_name.ilike(search_pattern),
                SupportContact.email.ilike(search_pattern),
                SupportContact.phone_number.ilike(search_pattern),
                SupportContact.whatsapp_number.ilike(search_pattern),
            )
        )

    needs_rule_join = bool(scope_type or scope_id or trip_type_scope)
    stmt = select(SupportContact).options(selectinload(SupportContact.routing_rules))
    count_stmt = select(func.count(func.distinct(SupportContact.id)))

    if needs_rule_join:
        stmt = stmt.join(SupportRoutingRule)
        count_stmt = count_stmt.select_from(SupportContact).join(SupportRoutingRule)
        if scope_type:
            filters.append(SupportRoutingRule.scope_type == scope_type)
        if scope_id:
            filters.append(SupportRoutingRule.scope_id == scope_id)
        if trip_type_scope:
            filters.append(
                SupportRoutingRule.trip_type_scope
                == _normalize_trip_type_scope(trip_type_scope)
            )
        if is_active is not None:
            filters.append(SupportRoutingRule.is_active == is_active)
    else:
        count_stmt = count_stmt.select_from(SupportContact)

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    result = await db.execute(
        stmt.order_by(SupportContact.created_at.desc()).offset(offset).limit(limit)
    )
    contacts = result.scalars().unique().all()

    return SupportContactListSchema(
        items=[SupportContactSchema.model_validate(contact) for contact in contacts],
        total=total,
        page=page,
        limit=limit,
    )


async def update_support_contact(
    contact_id: str,
    payload: SupportContactUpdate,
    db: AsyncSession,
    requestor: str,
    sync_routing_rules: bool = False,
) -> SupportContactSchema:
    try:
        contact = await _get_support_contact_model(
            contact_id=contact_id,
            db=db,
            include_inactive=True,
        )

        update_data = payload.model_dump(
            exclude_unset=True,
            exclude={"routing_rules"}, # We won't update routing rules here; they are handled separately below
        )
        for field, value in update_data.items():
            if field == "email" and value is not None:
                value = str(value)
            setattr(contact, field, value)

        if payload.routing_rules is not None:
            if sync_routing_rules:
                for existing_rule in list(contact.routing_rules):
                    await db.delete(existing_rule)
                await db.flush()

            for rule_payload in payload.routing_rules:
                await _create_routing_rule_model(
                    support_contact_id=contact.id,
                    payload=rule_payload,
                    db=db,
                    requestor=requestor,
                )

        await db.commit()
        return await get_support_contact_by_id(contact.id, db, include_inactive=True)
    except CabboException:
        await db.rollback()
        raise
    except IntegrityError as e:
        await db.rollback()
        log.error(f"Support contact update integrity error: {str(e)}")
        raise CabboException(
            "A support contact or routing rule with these details already exists.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    except Exception as e:
        await db.rollback()
        log.error(f"Error updating support contact {contact_id}: {str(e)}")
        raise CabboException(
            f"Failed to update support contact: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def delete_support_contact(contact_id: str, db: AsyncSession) -> bool:
    try:
        contact = await _get_support_contact_model(
            contact_id=contact_id,
            db=db,
            include_inactive=True,
        )
        if not contact.is_active:
            return True

        contact.is_active = False
        #Deactivate all associated routing rules
        for rule in contact.routing_rules:
            rule.is_active = False

        await db.commit()
        return True
    except CabboException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        log.error(f"Error deleting support contact {contact_id}: {str(e)}")
        raise CabboException(
            f"Failed to delete support contact: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def activate_support_contact(contact_id: str, db: AsyncSession) -> SupportContactSchema:
    try:
        contact = await _get_support_contact_model(
            contact_id=contact_id,
            db=db,
            include_inactive=True,
        )
        contact.is_active = True
        await db.commit()
        return await get_support_contact_by_id(contact.id, db, include_inactive=True)
    except CabboException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to activate support contact: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def create_support_routing_rule(
    support_contact_id: str,
    payload: SupportRoutingRuleCreate,
    db: AsyncSession,
    requestor: str,
) -> SupportRoutingRuleSchema:
    try:
        await _get_support_contact_model(
            contact_id=support_contact_id,
            db=db,
            include_inactive=True,
        )
        rule = await _create_routing_rule_model(
            support_contact_id=support_contact_id,
            payload=payload,
            db=db,
            requestor=requestor,
        )
        await db.commit()
        await db.refresh(rule)
        return SupportRoutingRuleSchema.model_validate(rule)
    except CabboException:
        await db.rollback()
        raise
    except IntegrityError as e:
        await db.rollback()
        log.error(f"Support routing rule integrity error: {str(e)}")
        raise CabboException(
            "A support routing rule with these details already exists for this contact.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to create support routing rule: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def update_support_routing_rule(
    rule_id: str,
    payload: SupportRoutingRuleUpdate,
    db: AsyncSession,
) -> SupportRoutingRuleSchema:
    try:
        rule = await _get_support_routing_rule_model(
            rule_id=rule_id,
            db=db,
            include_inactive=True,
        )

        update_data = payload.model_dump(exclude_unset=True)
        if "trip_type_scope" in update_data:
            update_data["trip_type_scope"] = _normalize_trip_type_scope(
                update_data["trip_type_scope"]
            )
        if any(
            field in update_data
            for field in ["scope_type", "scope_id", "country_id", "state_id", "region_id"]
        ):
            normalized_rule = SupportRoutingRuleCreate(
                scope_type=update_data.get("scope_type", rule.scope_type),
                scope_id=update_data.get("scope_id", rule.scope_id),
                country_id=update_data.get("country_id", rule.country_id),
                state_id=update_data.get("state_id", rule.state_id),
                region_id=update_data.get("region_id", rule.region_id),
                trip_type_scope=_normalize_trip_type_scope(
                    update_data.get("trip_type_scope", rule.trip_type_scope)
                ),
                priority=update_data.get("priority", rule.priority),
                is_active=update_data.get("is_active", rule.is_active),
            )
            await _validate_support_scope(normalized_rule, db)
            update_data.update(
                normalized_rule.model_dump(
                    include={
                        "scope_type",
                        "scope_id",
                        "country_id",
                        "state_id",
                        "region_id",
                        "trip_type_scope",
                        "priority",
                        "is_active",
                    }
                )
            )

        for field, value in update_data.items():
            setattr(rule, field, value)

        await db.commit()
        await db.refresh(rule)
        return SupportRoutingRuleSchema.model_validate(rule)
    except CabboException:
        await db.rollback()
        raise
    except IntegrityError as e:
        await db.rollback()
        log.error(f"Support routing rule update integrity error: {str(e)}")
        raise CabboException(
            "A support routing rule with these details already exists for this contact.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to update support routing rule: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def delete_support_routing_rule(rule_id: str, db: AsyncSession) -> bool:
    try:
        rule = await _get_support_routing_rule_model(
            rule_id=rule_id,
            db=db,
            include_inactive=True,
        )
        rule.is_active = False
        await db.commit()
        return True
    except CabboException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to delete support routing rule: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def get_best_support_contact(
    db: AsyncSession,
    support_type: SupportTypeEnum,
    trip_type_scope: TripTypeScope = "all",
    region_id: Optional[str] = None,
    state_id: Optional[str] = None,
    country_id: Optional[str] = None,
) -> Optional[SupportContactSchema]:
    trip_type_scope = _normalize_trip_type_scope(trip_type_scope)
    candidates = []
    if region_id:
        candidates.append((SupportScopeEnum.region, region_id, 1))
    if state_id:
        candidates.append((SupportScopeEnum.state, state_id, 2))
    if country_id:
        candidates.append((SupportScopeEnum.country, country_id, 3))

    for scope_type, scope_id, fallback_rank in candidates:
        stmt = (
            select(SupportContact)
            .join(SupportRoutingRule)
            .options(selectinload(SupportContact.routing_rules))
            .where(
                SupportContact.is_active == True,
                SupportContact.support_type == support_type,
                SupportRoutingRule.is_active == True,
                SupportRoutingRule.scope_type == scope_type,
                SupportRoutingRule.scope_id == scope_id,
                SupportRoutingRule.trip_type_scope.in_([trip_type_scope, "all"]),
            )
            .order_by(
                SupportRoutingRule.priority.asc(),  #Lower priority values win
                SupportRoutingRule.trip_type_scope.desc(),
                SupportContact.created_at.asc(), #Older contacts win if all else is equal
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        contact = result.scalars().first()
        if contact:
            log.info(
                f"Resolved support contact using fallback rank {fallback_rank}: {contact.id}"
            )
            return SupportContactSchema.model_validate(contact)

    return None


async def _create_routing_rule_model(
    support_contact_id: str,
    payload: SupportRoutingRuleCreate,
    db: AsyncSession,
    requestor: str,
) -> SupportRoutingRule:
    await _validate_support_scope(payload, db)
    rule = SupportRoutingRule(
        support_contact_id=support_contact_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        country_id=payload.country_id,
        state_id=payload.state_id,
        region_id=payload.region_id,
        trip_type_scope=_normalize_trip_type_scope(payload.trip_type_scope),
        priority=payload.priority,
        is_active=payload.is_active,
        created_by=requestor,
    )
    db.add(rule)
    await db.flush()
    return rule


def _normalize_trip_type_scope(trip_type_scope:TripTypeScope) -> str:
    if trip_type_scope is None or trip_type_scope == "":
        return "all"
    return getattr(trip_type_scope, "value", trip_type_scope)


def _get_or_create_seed_support_contact(
    db: Session,
    display_name: str,
    email: str,
    phone_number: str,
    whatsapp_number: Optional[str],
    created_by: str,
    support_type: SupportTypeEnum = SupportTypeEnum.customer,
    
) -> SupportContact:
    contact = (
        db.query(SupportContact)
        .filter(
            SupportContact.email == email,
            SupportContact.phone_number == phone_number,
            SupportContact.support_type == support_type,
        )
        .one_or_none()
    )
    if contact:
        contact.display_name = display_name
        contact.whatsapp_number = whatsapp_number
        contact.is_active = True
        return contact

    contact = SupportContact(
        display_name=display_name,
        email=email,
        phone_number=phone_number,
        whatsapp_number=whatsapp_number,
        support_type=SupportTypeEnum.customer,
        is_active=True,
        created_by=created_by,
    )
    db.add(contact)
    db.flush()
    return contact


def _get_or_create_seed_routing_rule(
    db: Session,
    contact: SupportContact,
    scope_type: SupportScopeEnum,
    scope_id: str,
    trip_type_scope: str,
    created_by: str,
) -> SupportRoutingRule:
    trip_type_scope = _normalize_trip_type_scope(trip_type_scope)
    rule = (
        db.query(SupportRoutingRule)
        .filter(
            SupportRoutingRule.support_contact_id == contact.id,
            SupportRoutingRule.scope_type == scope_type,
            SupportRoutingRule.scope_id == scope_id,
            SupportRoutingRule.trip_type_scope == trip_type_scope,
        )
        .one_or_none()
    )
    if rule:
        rule.is_active = True
        return rule

    country_id = scope_id if scope_type == SupportScopeEnum.country else None
    state_id = scope_id if scope_type == SupportScopeEnum.state else None
    region_id = scope_id if scope_type == SupportScopeEnum.region else None
    priority = {
        SupportScopeEnum.region: 10,
        SupportScopeEnum.state: 20,
        SupportScopeEnum.country: 100,
    }.get(scope_type, 100)

    rule = SupportRoutingRule(
        support_contact_id=contact.id,
        scope_type=scope_type,
        scope_id=scope_id,
        country_id=country_id,
        state_id=state_id,
        region_id=region_id,
        trip_type_scope=trip_type_scope,
        priority=priority,
        is_active=True,
        created_by=created_by,
    )
    db.add(rule)
    db.flush()
    return rule


async def _get_support_contact_model(
    contact_id: str,
    db: AsyncSession,
    include_inactive: bool = False,
) -> SupportContact:
    stmt = (
        select(SupportContact)
        .options(selectinload(SupportContact.routing_rules))
        .where(SupportContact.id == contact_id)
    )
    if not include_inactive:
        stmt = stmt.where(SupportContact.is_active == True)

    result = await db.execute(stmt)
    contact = result.scalars().one_or_none()
    if not contact:
        raise CabboException(
            f"Support contact with id {contact_id} not found",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    return contact


async def _get_support_routing_rule_model(
    rule_id: str,
    db: AsyncSession,
    include_inactive: bool = False,
) -> SupportRoutingRule:
    stmt = select(SupportRoutingRule).where(SupportRoutingRule.id == rule_id)
    if not include_inactive:
        stmt = stmt.where(SupportRoutingRule.is_active == True)

    result = await db.execute(stmt)
    rule = result.scalars().one_or_none()
    if not rule:
        raise CabboException(
            f"Support routing rule with id {rule_id} not found",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    return rule


async def _validate_support_scope(
    payload: SupportRoutingRuleCreate,
    db: AsyncSession,
) -> None:
    if payload.scope_type == SupportScopeEnum.country:
        model = CountryModel
    elif payload.scope_type == SupportScopeEnum.state:
        model = StateModel
    elif payload.scope_type == SupportScopeEnum.region:
        model = RegionModel
    else:
        raise CabboException(
            "Invalid support routing scope",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )

    result = await db.execute(
        select(model.id).where(model.id == payload.scope_id, model.is_serviceable == True)
    )
    if result.scalar_one_or_none() is None:
        raise CabboException(
            f"Active {payload.scope_type.value} with id {payload.scope_id} not found",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )



async def get_support_geography_ids(
    trip_type: TripTypeEnum,
    origin: LocationInfo,
    db: AsyncSession,
) -> tuple[str | None, str | None, str | None]:
    region_id = None
    state_id = None
    country_id = None

    if trip_type in [
        TripTypeEnum.local,
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
    ]:
        if origin.region_code:
            region = await async_get_region_by_code(origin.region_code, db)
            if region:
                region_id = region.id
                state_id = region.state_id
                country_id = region.country_id

    if not state_id and origin.state_code:
        state = await async_get_state_by_state_code(origin.state_code, db)
        if state:
            state_id = state.id
            country_id = country_id or state.country_id

    if not country_id and origin.country_code:
        country = await async_get_country_by_code(origin.country_code, db)
        if country:
            country_id = country.id

    if not country_id:
        country = await async_get_country_by_code(settings.COUNTRY_CODE, db)
        if country:
            country_id = country.id

    if trip_type == TripTypeEnum.outstation:
        region_id = None

    return region_id, state_id, country_id
