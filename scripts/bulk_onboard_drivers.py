import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List




PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

from core.constants import Environment
from core.security import RoleEnum
from services.environment_service import load_env
from services.validation_service import validate_driver_payloads
from models.driver.driver_schema import DriverReadSchema

DEFAULT_DRIVER_FILE = PROJECT_ROOT / "scripts" / "data" / "v1_drivers.yaml"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk onboard the curated v1 driver cohort from YAML."
    )
    parser.add_argument(
        "env_name",
        nargs="?",
        default=os.getenv("ENV", Environment.LOCAL.value),
        choices=[
            Environment.LOCAL.value,
            Environment.DEV.value,
            Environment.PROD.value,
        ],
        help="Environment to target (local, dev, prod). Defaults to ENV/local.",
    )
    parser.add_argument(
        "--file",
        default=str(DEFAULT_DRIVER_FILE),
        help="Path to driver YAML file.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually insert drivers. Without this flag the script only validates and previews.",
    )
    return parser.parse_args()


def load_driver_rows(path: Path) -> list[dict]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to read YAML files. Install it with `pip install PyYAML`."
        ) from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    rows = data.get("drivers")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a top-level `drivers` list.")
    return rows


def build_driver_payloads(rows: list[dict]):
    from models.financial.payments_enum import PaymentModeEnum
    from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum

    payloads = []
    for row in rows:
        payloads.append(
            DriverReadSchema(
                name=row.get("name"),
                avg_rating=row.get("avg_rating", 4.0),
                phone=row.get("phone"),
                secondary_phone=row.get("secondary_phone"),
                cab_registration_number=row.get("cab_registration_number"),
                cab_model_and_make=row.get("cab_model_and_make"),
                cab_type=CarTypeEnum(row.get("cab_type", CarTypeEnum.sedan)),
                fuel_type=FuelTypeEnum(row.get("fuel_type", FuelTypeEnum.diesel)),
                capacity=row.get("capacity", "4+1"),
                color=row.get("color", "White"),
                roof_carrier_available=row.get("roof_carrier_available", False),
                payment_mode=PaymentModeEnum(
                    row.get("payment_mode", PaymentModeEnum.gpay)
                ),
                payment_phone_number=row.get("payment_phone_number", row["phone"]),
            )
        )

    validate_driver_payloads(payloads, basic_validation=True)

    return payloads


async def create_drivers(payloads:List[DriverReadSchema]):
    from db.database import AsyncSessionLocal
    from services.driver_service import create_drivers_in_bulk

    async with AsyncSessionLocal() as db:
        return await create_drivers_in_bulk(
            payload=payloads,
            db=db,
            created_by=RoleEnum.driver_admin,
        )


async def run(env_name: str, file_path: str, execute: bool):
    os.environ["ENV"] = env_name.lower()
    load_env(
        load_env_file=True
    )  # Load the environment variables from the .env.<env_name> file
    payloads:List[DriverReadSchema] = build_driver_payloads(load_driver_rows(Path(file_path)))

    print(f"Loaded: {len(payloads)}")
    for payload in payloads:
        print(f"READY {payload.name} ({payload.cab_registration_number})")

    if not execute:
        print("Dry run only. Re-run with --execute to insert pending drivers.")
        return

    created_drivers = await create_drivers(payloads)
    print(f"Created: {len(created_drivers)}")
    for driver in created_drivers:
        print(f"CREATED {driver.name} ({driver.cab_registration_number})")


if __name__ == "__main__":
    args = parse_args()
    if sys.platform.startswith("win"):
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run(args.env_name, args.file, args.execute))
        finally:
            loop.close()
    else:
        asyncio.run(run(args.env_name, args.file, args.execute))
