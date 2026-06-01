import base64
import json
import logging
import os
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_repo_full_name(repo: str | None = None) -> str:
    value = (repo or os.getenv("GITHUB_REPO") or "").strip()
    if not value:
        return ""

    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/")
    elif value.startswith("http://github.com/"):
        value = value.removeprefix("http://github.com/")

    value = value.removesuffix(".git").strip("/")
    return value if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", value) else ""


def get_audit_repository_url() -> str:
    repo = normalize_repo_full_name()
    return f"https://github.com/{repo}" if repo else ""


def github_audit_enabled() -> bool:
    return _env_bool("GITHUB_AUDIT") and bool(normalize_repo_full_name()) and bool(os.getenv("GITHUB_TOKEN"))


def build_audit_block_document(block: Any) -> dict:
    match = block.match
    return {
        "schema": "bolao-copa-2026.audit-block.v1",
        "block_number": block.block_number,
        "match": {
            "id": match.id,
            "round": match.round,
            "stage": match.stage,
            "group_name": match.group_name,
            "kickoff_time": match.kickoff_time.isoformat(),
            "team1_name": match.team1_name,
            "team2_name": match.team2_name,
        },
        "created_at": block.created_at.isoformat(),
        "previous_hash": block.previous_hash,
        "hash": block.hash,
        "payload": block.payload,
        "verification": {
            "algorithm": "SHA-256",
            "canonical_payload": "json.dumps(payload, sort_keys=True, separators=(',', ':'))",
            "input": "canonical_payload + previous_hash",
        },
    }


def publish_audit_block_to_github(block: Any) -> dict:
    if not github_audit_enabled():
        return {"published": False, "reason": "disabled"}

    repo = normalize_repo_full_name()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    path = f"blocks/block_{block.block_number:06d}_match_{block.match_id}.json"
    url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    content = json.dumps(build_audit_block_document(block), ensure_ascii=False, sort_keys=True, indent=2)
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")

    existing = requests.get(url, headers=headers, timeout=10)
    if existing.status_code == 200:
        existing_content = (existing.json().get("content") or "").replace("\n", "")
        if existing_content and existing_content != encoded_content:
            raise RuntimeError(f"Arquivo de auditoria GitHub ja existe com conteudo divergente: {path}")
        return {
            "published": True,
            "path": path,
            "html_url": existing.json().get("html_url"),
            "already_exists": True,
        }
    if existing.status_code not in (404,):
        existing.raise_for_status()

    response = requests.put(
        url,
        headers=headers,
        json={
            "message": f"audit: bloco {block.block_number:06d} jogo {block.match_id}",
            "content": encoded_content,
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "published": True,
        "path": path,
        "html_url": data.get("content", {}).get("html_url"),
        "commit_url": data.get("commit", {}).get("html_url"),
        "already_exists": False,
    }


def publish_audit_block_best_effort(block: Any) -> dict:
    try:
        return publish_audit_block_to_github(block)
    except Exception as exc:
        logger.warning("Falha ao publicar bloco de auditoria %s no GitHub: %s", block.block_number, exc)
        return {"published": False, "reason": "error"}
