import os
import json
from typing import Dict, Optional
from fastapi import Request
from pydantic import ValidationError
from rich.console import Console
from models.geography.location_schema import CountrySchema, RegionSchema


