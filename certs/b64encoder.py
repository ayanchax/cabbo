import base64
from pathlib import Path

pem_string = Path("certs/db/prod-db-ca.pem").read_text(encoding="utf-8")

base64_cert = base64.b64encode(pem_string.encode("utf-8")).decode("utf-8")
print(base64_cert)