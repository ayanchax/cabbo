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

class GeographyRepository:
    """Holds all loaded country and region configurations."""

    def __init__(self):
        # mapping: country_code -> CountrySchema
        self.countries: Dict[str, CountrySchema] = {}
        # mapping: country_code -> region_code -> RegionSchema
        self.regions: Dict[str, Dict[str, RegionSchema]] = {}

    def add_country(self, country_code: str, country: CountrySchema):
        self.countries[country_code.upper()] = country

    def add_region(self, country_code: str, region_code: str, region: RegionSchema):
        country_code = country_code.upper()
        region_code = region_code.upper()
        self.regions.setdefault(country_code, {})[region_code] = region

    def get_country(self, country_code: str) -> Optional[CountrySchema]:
        return self.countries.get(country_code.upper())

    def get_region(self, country_code: str, region_code: str) -> Optional[RegionSchema]:
        return self.regions.get(country_code.upper(), {}).get(region_code.upper())


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
        # if header contains country:region like IN:BLR
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

def load_geographies() -> GeographyRepository:
    """Load country wise region configurations from the config/countries directory."""
    return initialize_geographies()

def initialize_geographies(base_path: str = None) -> GeographyRepository:
    """Load and validate all country/region JSON files under `config/countries`.

    Expects directory structure:
      config/countries/<COUNTRY>/country.json
      config/countries/<COUNTRY>/regions/<REGION>.json
    """
    console = Console()
    if base_path is None:
        base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "countries")

    store = GeographyRepository()

    if not os.path.isdir(base_path):
        console.print(f"[red]Config directory not found:[/red] {base_path}")
        return store

    for country_dir in os.listdir(base_path):
        country_path = os.path.join(base_path, country_dir)
        if not os.path.isdir(country_path):
            continue
        country_file = os.path.join(country_path, "country.json")
        if not os.path.isfile(country_file) or not country_file.lower().endswith(".json"):
            console.print(f"[yellow]Skipping {country_dir}: country.json not found[/yellow]")
            continue

        try:
            with open(country_file, "r", encoding="utf-8") as f:
                country_data = json.load(f)
        except FileNotFoundError:
            console.print(f"[yellow]Skipping {country_dir}: country.json not found[/yellow]")
            continue
        try:
            country = CountrySchema.model_validate(country_data)
            store.add_country(country.country_code, country)
        except ValidationError as e:
            console.print(f"[red]Invalid country config for {country_dir}:[/red]")
            console.print(e)
            raise

        # load regions
        regions_dir = os.path.join(country_path, "regions")
        if not os.path.isdir(regions_dir):
            console.print(f"[yellow]No regions directory for {country_dir}[/yellow]")
            continue
        for fname in os.listdir(regions_dir):
            if not os.path.isfile(fname) or not fname.lower().endswith(".json"):
                continue
            region_file = os.path.join(regions_dir, fname)
            try:
                with open(region_file, "r", encoding="utf-8") as f:
                    region_data = json.load(f)
            except Exception:
                console.print(f"[red]Failed to read region file {region_file}[/red]")
                raise
            try:
                region = RegionSchema.model_validate(region_data)
                store.add_region(country.country_code, region.region_code, region)
            except ValidationError as e:
                console.print(f"[red]Invalid region config {region_file}:[/red]")
                console.print(e)
                raise

    return store
