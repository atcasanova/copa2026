#!/usr/bin/env python3
"""
Generate a PostgreSQL backup and uploads archive, then send both to Telegram.

Expected environment variables:
  TELEGRAM_BACKUP_BOT_TOKEN
  TELEGRAM_BACKUP_CHAT_ID

The script also reads .env from the project root, when present, to find:
  POSTGRES_USER
  POSTGRES_DB
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = Path("/var/backups/copa2026")
DEFAULT_DB_CONTAINER = "bolao_db"
DEFAULT_UPLOADS_DIR = PROJECT_ROOT / "backend" / "uploads"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
TELEGRAM_MAX_FILE_BYTES = 49 * 1024 * 1024


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def env_value(name: str, dotenv: dict[str, str], default: str = "") -> str:
    return os.getenv(name) or dotenv.get(name) or default


def run_pg_dump(container: str, db_user: str, db_name: str, output_path: Path) -> None:
    command = [
        "docker",
        "exec",
        container,
        "pg_dump",
        "-U",
        db_user,
        "-d",
        db_name,
        "-F",
        "c",
    ]
    with output_path.open("wb") as output_file:
        result = subprocess.run(command, stdout=output_file, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        stderr = result.stderr.strip() or "sem detalhe no stderr"
        raise RuntimeError(f"pg_dump falhou com código {result.returncode}: {stderr}")


def gzip_file(source: Path, destination: Path) -> None:
    with source.open("rb") as src, gzip.open(destination, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)


def archive_uploads(uploads_dir: Path, output_path: Path) -> None:
    with tarfile.open(output_path, "w:gz") as archive:
        if uploads_dir.exists():
            archive.add(uploads_dir, arcname="uploads")
        else:
            empty_marker = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
            try:
                empty_marker.write("uploads directory not found\n")
                empty_marker.close()
                archive.add(empty_marker.name, arcname="uploads/README.txt")
            finally:
                Path(empty_marker.name).unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, metadata: dict) -> None:
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def telegram_api_request(token: str, method: str, body: bytes, content_type: str) -> dict:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de conexão com Telegram: {exc.reason}") from exc

    data = json.loads(payload)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram retornou erro: {payload}")
    return data


def multipart_body(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----copa2026-backup-{hashlib.sha256(str(file_path).encode()).hexdigest()[:16]}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])

    chunks.extend([
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{file_path.name}"\r\n'
        ).encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def send_telegram_document(token: str, chat_id: str, path: Path, caption: str) -> None:
    size = path.stat().st_size
    if size > TELEGRAM_MAX_FILE_BYTES:
        raise RuntimeError(
            f"{path.name} tem {size / 1024 / 1024:.1f} MB; "
            "acima do limite seguro de envio pelo Telegram Bot API."
        )

    fields = {"chat_id": chat_id, "caption": caption}
    body, content_type = multipart_body(fields, "document", path)
    telegram_api_request(token, "sendDocument", body, content_type)


def cleanup_old_backups(backup_dir: Path, keep_days: int) -> None:
    if keep_days <= 0:
        return

    cutoff = datetime.now().timestamp() - keep_days * 24 * 60 * 60
    for path in backup_dir.glob("copa2026_*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup Copa 2026 database/uploads and send to Telegram.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--db-container", default=DEFAULT_DB_CONTAINER)
    parser.add_argument("--db-user", default=None)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--uploads-dir", type=Path, default=DEFAULT_UPLOADS_DIR)
    parser.add_argument("--telegram-token", default=None)
    parser.add_argument("--telegram-chat-id", default=None)
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--skip-telegram", action="store_true", help="Generate local files only.")
    parser.add_argument("--dry-run", action="store_true", help="Show resolved configuration without generating files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dotenv = load_dotenv(PROJECT_ROOT / ".env")

    db_user = args.db_user or env_value("POSTGRES_USER", dotenv, "bolao_user")
    db_name = args.db_name or env_value("POSTGRES_DB", dotenv, "bolao_db")
    telegram_token = args.telegram_token or env_value("TELEGRAM_BACKUP_BOT_TOKEN", dotenv)
    telegram_chat_id = args.telegram_chat_id or env_value("TELEGRAM_BACKUP_CHAT_ID", dotenv)
    timestamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S")

    resolved = {
        "backup_dir": str(args.backup_dir),
        "db_container": args.db_container,
        "db_user": db_user,
        "db_name": db_name,
        "uploads_dir": str(args.uploads_dir),
        "telegram_configured": bool(telegram_token and telegram_chat_id),
        "keep_days": args.keep_days,
    }
    if args.dry_run:
        print(json.dumps(resolved, ensure_ascii=False, indent=2))
        return 0

    if not args.skip_telegram and (not telegram_token or not telegram_chat_id):
        print(
            "Erro: configure TELEGRAM_BACKUP_BOT_TOKEN e TELEGRAM_BACKUP_CHAT_ID, "
            "ou use --skip-telegram.",
            file=sys.stderr,
        )
        return 2

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    raw_dump = args.backup_dir / f"copa2026_db_{timestamp}.dump"
    db_backup = args.backup_dir / f"copa2026_db_{timestamp}.dump.gz"
    uploads_backup = args.backup_dir / f"copa2026_uploads_{timestamp}.tar.gz"
    manifest_path = args.backup_dir / f"copa2026_manifest_{timestamp}.json"

    print(f"Gerando pg_dump em {db_backup}...")
    run_pg_dump(args.db_container, db_user, db_name, raw_dump)
    gzip_file(raw_dump, db_backup)
    raw_dump.unlink(missing_ok=True)

    print(f"Compactando uploads em {uploads_backup}...")
    archive_uploads(args.uploads_dir, uploads_backup)

    files = [db_backup, uploads_backup]
    manifest = {
        "created_at": datetime.now(LOCAL_TZ).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "database": {"container": args.db_container, "name": db_name, "user": db_user},
        "uploads_dir": str(args.uploads_dir),
        "files": [
            {
                "name": file_path.name,
                "size_bytes": file_path.stat().st_size,
                "sha256": sha256_file(file_path),
            }
            for file_path in files
        ],
    }
    write_manifest(manifest_path, manifest)
    files.append(manifest_path)

    if not args.skip_telegram:
        print("Enviando arquivos para o Telegram...")
        send_telegram_document(
            telegram_token,
            telegram_chat_id,
            db_backup,
            f"Backup PostgreSQL Copa 2026 - {timestamp}",
        )
        send_telegram_document(
            telegram_token,
            telegram_chat_id,
            uploads_backup,
            f"Backup uploads Copa 2026 - {timestamp}",
        )
        send_telegram_document(
            telegram_token,
            telegram_chat_id,
            manifest_path,
            f"Manifesto backup Copa 2026 - {timestamp}",
        )

    cleanup_old_backups(args.backup_dir, args.keep_days)

    print("Backup concluído:")
    for file_path in files:
        print(f"- {file_path} ({file_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Backup interrompido pelo usuário.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
