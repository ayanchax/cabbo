import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from db.database import get_mysql_local_session
from services.seed_data_service import run_seed_registry


def run():
    with get_mysql_local_session() as session:
        run_seed_registry(session)


if __name__ == "__main__":
    run()
