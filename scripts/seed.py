import os
import sys
import logging
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from services.environment_service import load_env
from core.constants import Environment

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed the configured database environment"
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
        help="Environment to seed (local, dev, prod)",
    )
    return parser.parse_args()


def run(env_name: str = Environment.LOCAL.value):
    env_name = env_name.lower()
    os.environ["ENV"] = env_name
    load_env(load_env_file=True)  # Load the environment variables from the .env file

    from db.database import get_mysql_local_session
    from services.seed_data_service import run_seed_registry

    with get_mysql_local_session() as session:
        run_seed_registry(session)


if __name__ == "__main__":
    args = parse_args()
    run(args.env_name)
