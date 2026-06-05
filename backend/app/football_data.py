import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from .models import AuditLog, Match, Prediction
from .notifications import send_general_ranking_notification
from .scoring import capture_ranking_snapshot, invalidate_ranking_cache, score_prediction
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


def _fetch_matches(date_from: datetime, date_to: datetime) -> list[dict]:
    token = get_api_token()
    if not token:
        return []

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
    return payload.get("matches", [])


def _max_requests_per_run() -> int:
    try:
        return max(1, int(os.getenv("FOOTBALL_DATA_MAX_REQUESTS_PER_RUN", "8")))
    except ValueError:
        return 8


def _find_api_match(local_match: Match, api_matches: list[dict]) -> ApiMatchResult | None:
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

        return _extract_regulation_score(api_match)

    return None


def _candidate_kickoff_times(db: Session, now_utc: datetime) -> list[datetime]:
    cutoff = now_utc - timedelta(hours=POLL_AFTER_HOURS)
    rows = db.query(Match.kickoff_time).filter(
        Match.kickoff_time <= cutoff,
        Match.status.notin_(["postponed", "cancelled", "score_confirmed", "finished"]),
        Match.score_ft_team1 == None,
        Match.score_ft_team2 == None,
    ).distinct().order_by(Match.kickoff_time.asc()).all()
    return [row[0] for row in rows]


def sync_finished_scores_from_football_data(db: Session, now_utc: datetime | None = None) -> dict:
    if not football_data_enabled():
        return {"enabled": False, "checked_groups": 0, "updated_groups": 0, "updated_matches": 0, "errors": []}
    if not get_api_token():
        return {"enabled": True, "checked_groups": 0, "updated_groups": 0, "updated_matches": 0, "errors": ["FOOTBALL_DATA_API não configurado."]}

    now_utc = now_utc or datetime.utcnow()
    kickoff_times = _candidate_kickoff_times(db, now_utc)
    result = {"enabled": True, "checked_groups": 0, "updated_groups": 0, "updated_matches": 0, "errors": []}
    response_cache: dict[tuple[str, str], list[dict]] = {}
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
            continue

        date_from = kickoff_time - timedelta(days=1)
        date_to = kickoff_time + timedelta(days=1)
        cache_key = (date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d"))
        try:
            if cache_key not in response_cache:
                if requests_made >= _max_requests_per_run():
                    result["errors"].append("Limite de consultas football-data.org por execução atingido.")
                    break
                response_cache[cache_key] = _fetch_matches(date_from, date_to)
                requests_made += 1
            api_matches = response_cache[cache_key]
        except Exception as exc:
            db.rollback()
            logger.warning("Falha ao consultar football-data.org para %s: %s", kickoff_time, exc)
            result["errors"].append(f"{kickoff_time.isoformat()}: {exc}")
            continue

        api_results = {}
        for match in matches:
            api_result = _find_api_match(match, api_matches)
            if not api_result:
                api_results = {}
                break
            api_results[match.id] = api_result

        if len(api_results) != len(matches):
            continue

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
                score_prediction(db, prediction, match)

        db.commit()
        invalidate_ranking_cache(db)
        capture_ranking_snapshot(db)
        send_general_ranking_notification(db)
        result["updated_groups"] += 1
        result["updated_matches"] += len(matches)

    return result
