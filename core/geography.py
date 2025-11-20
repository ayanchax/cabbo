from typing import Optional
from fastapi import Request
from typing import Optional
from fastapi import Request
from fastapi.params import Depends
from db.database import get_mysql_session
from models.geography.region_schema import RegionSchema
from services.geography_service import (
    get_all_countries,
    get_region,
    get_regions_by_country,
)
from sqlalchemy.orm import Session


def resolve_region_from_request(
    request: Request, db: Session = Depends(get_mysql_session)
) -> Optional[RegionSchema]:
    """Resolve a region for the incoming request using the following priority:
    1. X-App-Region header
    2. ?region= query parameter
    4. fallback to first supported region of the first country in the data store
    Returns the RegionSchema or None if not found.
    """

    header_region = request.headers.get("x-app-region")
    if header_region:
        # if header contains country:region like IN:KA:BLR
        if ":" in header_region:
            country_code, state_code, region_code = header_region.split(":")
            return get_region(country_code, state_code, region_code, db)

    # query param
    q_region = request.query_params.get("region")
    if q_region:
        if ":" in q_region:
            country_code, state_code, region_code = q_region.split(":")
            return get_region(country_code, state_code, region_code, db)

    # fallback: pick the first country/first region available
    for country in get_all_countries(db):
        if country.country_code:
            regions_in_country = get_regions_by_country(country.country_code, db)
            if regions_in_country and len(regions_in_country) > 0:
                return regions_in_country[0]

    return None
