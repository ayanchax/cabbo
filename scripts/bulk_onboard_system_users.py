import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))
from models.user.user_schema import UserCreateSchema
from core.constants import Environment
from services.environment_service import load_env
from services.validation_service import validate_system_user_payloads
from models.driver.driver_schema import DriverReadSchema
DEFAULT_SYSTEM_USER_FILE = PROJECT_ROOT / "scripts" / "data" / "v1_system_users.yaml"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk onboard the curated v1 system user cohort from YAML."
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
        default=str(DEFAULT_SYSTEM_USER_FILE),
        help="Path to system user YAML file.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually insert system users. Without this flag the script only validates and previews.",
    )
    return parser.parse_args()


def load_system_user_rows(path: Path) -> list[dict]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to read YAML files. Install it with `pip install PyYAML`."
        ) from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    rows = data.get("users")
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a top-level `users` list.")
    return rows


def build_system_user_payloads(rows: list[dict]):
    payloads = []
    for row in rows:
        payloads.append(
            UserCreateSchema(
                name=row.get("name"),
                username=row.get("username"),
                phone_number=row.get("phone_number"),
                role=row.get("role"),
            )
        )

    validate_system_user_payloads(payloads)

    return payloads


async def create_system_users(payloads: List[UserCreateSchema]):
    from db.database import AsyncSessionLocal
    from services.user_service import create_users_in_bulk

    async with AsyncSessionLocal() as db:
        return await create_users_in_bulk(
            payload=payloads,
            db=db,
        )


async def run(env_name: str, file_path: str, execute: bool):
    os.environ["ENV"] = env_name.lower()
    load_env(
        load_env_file=True
    )  # Load the environment variables from the .env.<env_name> file
    payloads: List[UserCreateSchema] = build_system_user_payloads(
        load_system_user_rows(Path(file_path))
    )

    print(f"Loaded: {len(payloads)}")
    for payload in payloads:
        print(f"READY {payload.name}")

    if not execute:
        print("Dry run only. Re-run with --execute to insert pending system users.")
        return

    created_system_users = await create_system_users(payloads)
    print(f"Created: {len(created_system_users)}")
    for user in created_system_users:
        print(f"CREATED {user.name}")


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
