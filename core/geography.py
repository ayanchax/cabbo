from typing import Optional
from fastapi import Request
from pydantic_core import ValidationError
import os
import json
from typing import Dict, Optional
from fastapi import Request
from pydantic import ValidationError
from rich.console import Console

from models.geography.country_schema import CountrySchema
from models.geography.region_schema import RegionSchema

 

def resolve_region_from_request(request: Request, default_country: str = None) -> Optional[RegionSchema]:
    """Resolve a region for the incoming request using the following priority:
    1. X-App-Region header
    2. ?region= query parameter
    3. request.state or app.state default region
    4. fallback to first supported region of default country
    Returns the RegionSchema or None if not found.
    """
    app = request.app
    store: GeographyRepository = getattr(app.state, "config_store", None)
    if not store:
        return None

    # header
    header_region = request.headers.get("x-app-region")
    if header_region:
        # if header contains country:region like IN:KA:BLR
        if ":" in header_region:
            country_code, region_code = header_region.split(":", 1)
            return store.get_region(country_code, region_code)
        # otherwise try to find region across countries
        for c in store.countries:
            r = store.get_region(c, header_region)
            if r:
                return r

    # query param
    q_region = request.query_params.get("region")
    if q_region:
        if ":" in q_region:
            country_code, region_code = q_region.split(":", 1)
            return store.get_region(country_code, region_code)
        for c in store.countries:
            r = store.get_region(c, q_region)
            if r:
                return r

    # app state defaults
    if default_country:
        default_country_obj = store.get_country(default_country)
        if default_country_obj and default_country_obj.supported_regions:
            first_region = default_country_obj.supported_regions[0]
            return store.get_region(default_country, first_region)

    # fallback: pick the first country/first region available
    for ccode, country in store.countries.items():
        if country.supported_regions:
            return store.get_region(ccode, country.supported_regions[0])

    return None

 