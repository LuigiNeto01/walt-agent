#!/usr/bin/env python3
"""Deploy walt-agent to the home server via SSH/SFTP.

The script intentionally does not store secrets. It reads deployment settings
from environment variables and production app settings from backend/.env.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

import paramiko


LOCAL_DIR = Path(__file__).resolve().parent
BACKEND_ENV = LOCAL_DIR / "backend" / ".env"

DEPLOY_HOST = os.getenv("DEPLOY_HOST", "192.168.0.12")
DEPLOY_USER = os.getenv("DEPLOY_USER", "luigi")
DEPLOY_PASSWORD = os.getenv("DEPLOY_PASSWORD")
DEPLOY_PUBLIC_HOSTS = [
    host.strip()
    for host in os.getenv("DEPLOY_PUBLIC_HOSTS", "").split(",")
    if host.strip()
]
REMOTE_DIR = os.getenv("DEPLOY_REMOTE_DIR", "/home/luigi/walt-agent")

EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
EXCLUDE_FILES = {".env"}


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(f"Arquivo {path} nao encontrado. Crie a partir de backend/.env.example.")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def build_prod_env() -> str:
    env = read_env_file(BACKEND_ENV)
    cors_origins = [
        origin.strip()
        for origin in env.get("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    for origin in (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        f"http://{DEPLOY_HOST}:5173",
        f"http://{DEPLOY_HOST}:8000",
    ):
        if origin not in cors_origins:
            cors_origins.append(origin)
    for host in DEPLOY_PUBLIC_HOSTS:
        for origin in (f"http://{host}:5173", f"http://{host}:8000"):
            if origin not in cors_origins:
                cors_origins.append(origin)

    env.update(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://walt:walt@db:5432/walt_agent",
            "SSH_COMMAND_TIMEOUT": env.get("SSH_COMMAND_TIMEOUT", "120") or "120",
            "CORS_ORIGINS": ",".join(cors_origins),
        }
    )

    ordered_keys = [
        "APP_NAME",
        "APP_ENV",
        "API_V1_PREFIX",
        "DATABASE_URL",
        "INIT_DB_ON_STARTUP",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "AGENT_SYSTEM_PROMPT",
        "CORS_ORIGINS",
        "WAKE_ON_LAN_ENABLED",
        "WAKE_TARGET_MAC",
        "WAKE_BROADCAST_IP",
        "WAKE_PORT",
        "SSH_ENABLED",
        "SSH_HOST",
        "SSH_PORT",
        "SSH_USERNAME",
        "SSH_PASSWORD",
        "SSH_KEY_PATH",
        "SSH_COMMAND_TIMEOUT",
        "SSH_OUTPUT_LIMIT",
        "SSH_FILE_TEXT_LIMIT",
        "SSH_PYTHON_COMMAND",
        "SSH_DESKTOP_USERNAME",
        "SSH_DESKTOP_PASSWORD",
    ]
    lines = [f"{key}={env.get(key, '')}" for key in ordered_keys]
    return "\n".join(lines) + "\n"


def run(ssh: paramiko.SSHClient, cmd: str) -> str:
    print(f"  $ {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if out:
        print(f"    {out}")
    if err:
        print(f"    [stderr] {err}")
    return out


def sftp_mkdir_p(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    parts = remote_path.split("/")
    current = ""
    for part in parts:
        if not part:
            current = "/"
            continue
        current = f"{current}/{part}" if current != "/" else f"/{part}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in path.parts) or path.name in EXCLUDE_FILES


def upload_dir(sftp: paramiko.SFTPClient, local_path: Path, remote_path: str) -> None:
    sftp_mkdir_p(sftp, remote_path)
    for item in local_path.iterdir():
        relative = item.relative_to(LOCAL_DIR)
        if should_skip(relative):
            continue
        remote_item = f"{remote_path}/{item.name}"
        if item.is_dir():
            upload_dir(sftp, item, remote_item)
        else:
            print(f"  uploading {relative} -> {remote_item}")
            sftp.put(str(item), remote_item)


def main() -> None:
    password = DEPLOY_PASSWORD or getpass.getpass(f"Senha SSH de {DEPLOY_USER}@{DEPLOY_HOST}: ")

    print(f"Connecting to {DEPLOY_USER}@{DEPLOY_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(DEPLOY_HOST, username=DEPLOY_USER, password=password)
    print("Connected.\n")

    print("=== Containers ativos no servidor ===")
    run(ssh, "docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'")
    print()

    print(f"=== Criando {REMOTE_DIR} ===")
    run(ssh, f"mkdir -p {REMOTE_DIR}/backend")
    print()

    print("=== Enviando arquivos ===")
    sftp = ssh.open_sftp()
    upload_dir(sftp, LOCAL_DIR, REMOTE_DIR)

    print("  writing backend/.env (producao)")
    with sftp.open(f"{REMOTE_DIR}/backend/.env", "w") as remote_env:
        remote_env.write(build_prod_env())

    sftp.close()
    print()

    print("=== Iniciando containers ===")
    run(ssh, f"cd {REMOTE_DIR} && docker compose up -d --build 2>&1 | tail -30")
    print()

    print("=== Status final ===")
    run(ssh, "docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'")

    ssh.close()
    print("\nDeploy concluido!")
    print(f"  Frontend: http://{DEPLOY_HOST}:5173")
    print(f"  API:      http://{DEPLOY_HOST}:8000/api/v1")


if __name__ == "__main__":
    main()
