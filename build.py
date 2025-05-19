#!/usr/bin/env python3
import argparse
import subprocess
import sys
from core.constants import APP_NAME

parser = argparse.ArgumentParser(description="Build and optionally run Cabbo Docker images.")
parser.add_argument("--env", choices=["dev", "prod"], default="dev", help="Environment to build for (dev or prod)")
parser.add_argument("--run", action="store_true", default=False, help="Run the container after building")
parser.add_argument("--port", default="8000", help="Port to expose (default: 8000)") # Expose port 8000 for the app to be accessible from outside the container
args = parser.parse_args()

if args.env == "dev":
    dockerfile = "Dockerfile.dev"
    tag = f"{APP_NAME}-dev"
    env_file = ".env.dev"
else:
    dockerfile = "Dockerfile" # Default to Dockerfile for production
    tag = f"{APP_NAME}-prod"
    env_file = ".env.prod"

build_cmd = [
    "docker", "build", "-f", dockerfile, "-t", tag, "."
]
print(f"Building Docker image for {args.env}...")
if subprocess.call(build_cmd) != 0:
    sys.exit("Docker build failed.")

if args.run:
    run_cmd = [
        "docker", "run", "-p", f"{args.port}:8000", "--env-file", env_file, tag
    ]
    print(f"Running Docker container for {args.env} on port {args.port}...")
    subprocess.call(run_cmd)
else:
    print(f"Docker image '{tag}' built successfully.")
