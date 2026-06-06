import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from .models import AuditLog, FootballDataSyncLog, Match, Prediction
from .notifications import send_general_ranking_notification
from .scoring import (
    capture_ranking_snapshot, capture_ranking_update_snapshot, invalidate_ranking_cache,
    load_stage_multipliers, score_prediction
)
from .sync import translate_team_name

logger = logging.getLogger("football_data")

DEFAULT_BASE_URL = "https://api.football-data.org/v4"
POLL_AFTER_HOURS = 2
KICKOFF_TOLERANCE_MINUTES = 20


@dataclass
class ApiMatchResult:
    api_id: int | None
    home_score: int
    away_score: int


def football_data_enabled() -> bool:
    return os.getenv("FOOTBALL_DATA_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def get_api_token() -> str | None:
    return os.getenv("FOOTBALL_DATA_API") or os.getenv("FOOTBALL_DATA_API_KEY")


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    value = translate_team_name(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _api_team_matches_local(api_team: dict, local_name: str, local_fifa_code: str | None = None) -> bool:
    local_candidates = {_normalize(local_name)}
    if local_fifa_code:
        local_candidates.add(_normalize(local_fifa_code))

    api_candidates = {
        _normalize(api_team.get("name")),
        _normalize(api_team.get("shortName")),
        _normalize(api_team.get("tla")),
    }
    api_candidates.discard("")
    return bool(local_candidates.intersection(api_candidates))


def _score_value(score_node: dict, side: str) -> int | None:
    value = score_node.get(side)
    if value is None:
        value = score_node.get("homeTeam" if side == "home" else "awayTeam")
    return value if isinstance(value, int) else None


def _now_iso() -> str:
    return f"{datetime.utcnow().isoformat(timespec='seconds')}Z"


def _append_event(events: list[dict], level: str, message: str, **extra) -> None:
    payload = {
        "timestamp": _now_iso(),
        "level": level,
        "message": message,
    }
    payload.update({key: value for key, value in extra.items() if value is not None})
    events.append(payload)


def _api_match_summary(api_match: dict | None) -> dict | None:
    if not api_match:
        return None
    score = api_match.get("score") or {}
    full_time = score.get("fullTime") or {}
    regular_time = score.get("regularTime") or {}
    home_team = api_match.get("homeTeam") or {}
    away_team = api_match.get("awayTeam") or {}
    return {
        "id": api_match.get("id"),
        "status": api_match.get("status"),
        "utcDate": api_match.get("utcDate"),
        "homeTeam": home_team.get("name") or home_team.get("shortName") or home_team.get("tla"),
        "awayTeam": away_team.get("name") or away_team.get("shortName") or away_team.get("tla"),
        "duration": score.get("duration"),
        "fullTime": full_time,
        "regularTime": regular_time,
    }


def _create_sync_log(db: Session, trigger: str, details: dict) -> FootballDataSyncLog:
    log = FootballDataSyncLog(
        trigger=trigger,
        status="running",
        details=details,
        errors=[],
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _update_sync_log(
    db: Session,
    log_id: int | None,
    result: dict,
    details: dict,
    status: str | None = None,
    finished: bool = False,
) -> None:
    if not log_id:
        return
    try:
        log = db.query(FootballDataSyncLog).filter(FootballDataSyncLog.id == log_id).first()
        if not log:
            return
        log.status = status or log.status
        log.checked_groups = result.get("checked_groups", 0)
        log.updated_groups = result.get("updated_groups", 0)
        log.updated_matches = result.get("updated_matches", 0)
        log.errors = result.get("errors", [])
        log.details = details
        if finished:
            log.finished_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()


def _extract_regulation_score(api_match: dict) -> ApiMatchResult | None:
    if api_match.get("status") != "FINISHED":
        return None

    score = api_match.get("score") or {}
    duration = score.get("duration") or "REGULAR"
    score_node = score.get("regularTime") if duration != "REGULAR" else score.get("fullTime")
    if not score_node:
        score_node = score.get("fullTime") if duration == "REGULAR" else None
    if not score_node:
        return None

    home_score = _score_value(score_node, "home")
    away_score = _score_value(score_node, "away")
    if home_score is None or away_score is None:
        return None

    return ApiMatchResult(
        api_id=api_match.get("id"),
        home_score=home_score,
        away_score=away_score,
    )


def _fetch_matches(date_from: datetime, date_to: datetime) -> tuple[list[dict], dict]:
    token = get_api_token()
    if not token:
        return [], {"configured": False, "returned_matches": 0}

    base_url = os.getenv("FOOTBALL_DATA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    competition = os.getenv("FOOTBALL_DATA_COMPETITION", "WC").strip()
    endpoint = (
        f"{base_url}/competitions/{competition}/matches"
        if competition
        else f"{base_url}/matches"
    )

    response = requests.get(
        endpoint,
        headers={"X-Auth-Token": token},
        params={
            "dateFrom": date_from.strftime("%Y-%m-%d"),
            "dateTo": date_to.strftime("%Y-%m-%d"),
        },
        timeout=int(os.getenv("FOOTBALL_DATA_TIMEOUT_SECONDS", "10")),
    )
    response.raise_for_status()
    payload = response.json()
    matches = payload.get("matches", [])
    meta = {
        "configured": True,
        "endpoint": endpoint,
        "competition": competition,
        "dateFrom": date_from.strftime("%Y-%m-%d"),
        "dateTo": date_to.strftime("%Y-%m-%d"),
        "status_code": getattr(response, "status_code", None),
        "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "returned_matches": len(matches),
        "sample": [_api_match_summary(match) for match in matches[:5]],
    }
    return matches, meta


def _max_requests_per_run() -> int:
    try:
        return max(1, int(os.getenv("FOOTBALL_DATA_MAX_REQUESTS_PER_RUN", "8")))
    except ValueError:
        return 8


def _inspect_api_match(local_match: Match, api_matches: list[dict]) -> tuple[ApiMatchResult | None, str, dict | None]:
    local_kickoff = local_match.kickoff_time
    local_team1_code = getattr(local_match.team1, "fifa_code", None)
    local_team2_code = getattr(local_match.team2, "fifa_code", None)

    for api_match in api_matches:
        api_kickoff = _parse_utc_datetime(api_match.get("utcDate"))
        if not api_kickoff:
            continue
        if abs(api_kickoff - local_kickoff) > timedelta(minutes=KICKOFF_TOLERANCE_MINUTES):
            continue

        home_team = api_match.get("homeTeam") or {}
        away_team = api_match.get("awayTeam") or {}
        if not _api_team_matches_local(home_team, local_match.team1_name, local_team1_code):
            continue
        if not _api_team_matches_local(away_team, local_match.team2_name, local_team2_code):
            continue

        api_result = _extract_regulation_score(api_match)
        if api_result:
            return api_result, "ok", _api_match_summary(api_match)
        if api_match.get("status") != "FINISHED":
            return None, f"Partida encontrada na API, mas status ainda é {api_match.get('status')}.", _api_match_summary(api_match)
        return None, "Partida encontrada na API, mas o placar final/regulamentar veio incompleto ou inesperado.", _api_match_summary(api_match)

    return None, "Nenhuma partida compatível encontrada no retorno da API.", None


def _find_api_match(local_match: Match, api_matches: list[dict]) -> ApiMatchResult | None:
    api_result, _, _ = _inspect_api_match(local_match, api_matches)
    return api_result


def _candidate_kickoff_times(db: Session, now_utc: datetime) -> list[datetime]:
    cutoff = now_utc - timedelta(hours=POLL_AFTER_HOURS)
    rows = db.query(Match.kickoff_time).filter(
        Match.kickoff_time <= cutoff,
        Match.status.notin_(["postponed", "cancelled", "score_confirmed", "finished"]),
        Match.score_ft_team1 == None,
        Match.score_ft_team2 == None,
    ).distinct().order_by(Match.kickoff_time.asc()).all()
    return [row[0] for row in rows]


def sync_finished_scores_from_football_data(
    db: Session,
    now_utc: datetime | None = None,
    trigger: str = "manual",
) -> dict:
    details = {
        "events": [],
        "candidate_kickoffs": [],
        "requests_made": 0,
    }
    _append_event(details["events"], "info", "Iniciando consulta ao football-data.org.", trigger=trigger)
    sync_log = _create_sync_log(db, trigger, details)

    if not football_data_enabled():
        result = {"enabled": False, "checked_groups": 0, "updated_groups": 0, "updated_matches": 0, "errors": []}
        _append_event(details["events"], "warning", "Sincronização football-data.org desabilitada por configuração.")
        _update_sync_log(db, sync_log.id, result, details, status="skipped", finished=True)
        return result
    if not get_api_token():
        result = {"enabled": True, "checked_groups": 0, "updated_groups": 0, "updated_matches": 0, "errors": ["FOOTBALL_DATA_API não configurado."]}
        _append_event(details["events"], "error", "FOOTBALL_DATA_API não configurado.")
        _update_sync_log(db, sync_log.id, result, details, status="error", finished=True)
        return result

    now_utc = now_utc or datetime.utcnow()
    kickoff_times = _candidate_kickoff_times(db, now_utc)
    result = {"enabled": True, "checked_groups": 0, "updated_groups": 0, "updated_matches": 0, "errors": []}
    details["candidate_kickoffs"] = [kickoff_time.isoformat() for kickoff_time in kickoff_times]
    _append_event(
        details["events"],
        "info",
        f"{len(kickoff_times)} horário(s) candidato(s) encontrado(s) para consulta.",
        candidate_kickoffs=details["candidate_kickoffs"],
    )
    _update_sync_log(db, sync_log.id, result, details)

    response_cache: dict[tuple[str, str], tuple[list[dict], dict]] = {}
    requests_made = 0

    for kickoff_time in kickoff_times:
        result["checked_groups"] += 1
        matches = db.query(Match).filter(
            Match.kickoff_time == kickoff_time,
            Match.status.notin_(["postponed", "cancelled", "score_confirmed", "finished"]),
            Match.score_ft_team1 == None,
            Match.score_ft_team2 == None,
        ).order_by(Match.id.asc()).all()
        if not matches:
            _append_event(
                details["events"],
                "info",
                "Horário candidato ignorado porque não há partidas pendentes sem placar.",
                kickoff_time=kickoff_time.isoformat(),
            )
            _update_sync_log(db, sync_log.id, result, details)
            continue

        group_matches = [
            {
                "id": match.id,
                "label": f"{match.team1_name} x {match.team2_name}",
                "status": match.status,
            }
            for match in matches
        ]
        _append_event(
            details["events"],
            "info",
            f"Consultando horário {kickoff_time.isoformat()} com {len(matches)} partida(s) local(is).",
            kickoff_time=kickoff_time.isoformat(),
            matches=group_matches,
        )

        date_from = kickoff_time - timedelta(days=1)
        date_to = kickoff_time + timedelta(days=1)
        cache_key = (date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d"))
        try:
            if cache_key not in response_cache:
                if requests_made >= _max_requests_per_run():
                    result["errors"].append("Limite de consultas football-data.org por execução atingido.")
                    _append_event(details["events"], "warning", "Limite de consultas por execução atingido.")
                    _update_sync_log(db, sync_log.id, result, details, status="warning")
                    break
                response_cache[cache_key] = _fetch_matches(date_from, date_to)
                requests_made += 1
                details["requests_made"] = requests_made
            api_matches, request_meta = response_cache[cache_key]
            _append_event(
                details["events"],
                "info",
                f"API retornou {len(api_matches)} partida(s) para a janela consultada.",
                kickoff_time=kickoff_time.isoformat(),
                request=request_meta,
            )
            _update_sync_log(db, sync_log.id, result, details)
        except Exception as exc:
            db.rollback()
            logger.warning("Falha ao consultar football-data.org para %s: %s", kickoff_time, exc)
            result["errors"].append(f"{kickoff_time.isoformat()}: {exc}")
            _append_event(
                details["events"],
                "error",
                "Falha HTTP/parse ao consultar football-data.org.",
                kickoff_time=kickoff_time.isoformat(),
                error=str(exc),
            )
            _update_sync_log(db, sync_log.id, result, details, status="warning")
            continue

        api_results = {}
        match_checks = []
        stage_multipliers = load_stage_multipliers(db)
        for match in matches:
            api_result, reason, api_summary = _inspect_api_match(match, api_matches)
            check = {
                "match_id": match.id,
                "local_match": f"{match.team1_name} x {match.team2_name}",
                "result": "ok" if api_result else "waiting_or_unexpected",
                "reason": reason,
                "api_match": api_summary,
            }
            if not api_result:
                api_results = {}
                match_checks.append(check)
                break
            check["score"] = {
                "team1": api_result.home_score,
                "team2": api_result.away_score,
                "api_id": api_result.api_id,
            }
            match_checks.append(check)
            api_results[match.id] = api_result

        if len(api_results) != len(matches):
            _append_event(
                details["events"],
                "warning",
                "Retorno da API ainda não contém todos os resultados esperados para este horário. Nenhum placar foi aplicado.",
                kickoff_time=kickoff_time.isoformat(),
                checks=match_checks,
            )
            _update_sync_log(db, sync_log.id, result, details, status="warning")
            continue

        _append_event(
            details["events"],
            "success",
            "Todos os resultados esperados foram encontrados para este horário. Aplicando placares.",
            kickoff_time=kickoff_time.isoformat(),
            checks=match_checks,
        )

        for match in matches:
            api_result = api_results[match.id]
            old_value = {
                "score_ft_team1": match.score_ft_team1,
                "score_ft_team2": match.score_ft_team2,
                "status": match.status,
            }
            match.score_ft_team1 = api_result.home_score
            match.score_ft_team2 = api_result.away_score
            match.score_et_team1 = None
            match.score_et_team2 = None
            match.score_pen_team1 = None
            match.score_pen_team2 = None
            match.status = "score_confirmed"
            match.score_confirmed_by_admin = False
            db.flush()

            db.add(AuditLog(
                user_id=None,
                action="football_data_score_auto_update",
                target_type="match",
                target_id=str(match.id),
                old_value=old_value,
                new_value={
                    "score_ft_team1": match.score_ft_team1,
                    "score_ft_team2": match.score_ft_team2,
                    "status": match.status,
                    "football_data_match_id": api_result.api_id,
                },
                reason="Resultado automático via football-data.org",
            ))
            predictions = db.query(Prediction).filter(Prediction.match_id == match.id).all()
            for prediction in predictions:
                score_prediction(db, prediction, match, stage_multipliers)

        db.commit()
        invalidate_ranking_cache(db)
        capture_ranking_snapshot(db)
        capture_ranking_update_snapshot(db, kickoff_time=kickoff_time)
        send_general_ranking_notification(db)
        result["updated_groups"] += 1
        result["updated_matches"] += len(matches)
        _append_event(
            details["events"],
            "success",
            f"{len(matches)} placar(es) aplicado(s), ranking recalculado e notificação avaliada.",
            kickoff_time=kickoff_time.isoformat(),
            updated_match_ids=[match.id for match in matches],
        )
        _update_sync_log(db, sync_log.id, result, details)

    has_warnings = any(event.get("level") == "warning" for event in details["events"])
    if result["errors"] or has_warnings:
        final_status = "warning"
    elif result["checked_groups"] == 0:
        final_status = "success"
    else:
        final_status = "success"
    _append_event(
        details["events"],
        "info",
        "Consulta football-data.org finalizada.",
        checked_groups=result["checked_groups"],
        updated_groups=result["updated_groups"],
        updated_matches=result["updated_matches"],
        errors=result["errors"],
    )
    _update_sync_log(db, sync_log.id, result, details, status=final_status, finished=True)
    return result
