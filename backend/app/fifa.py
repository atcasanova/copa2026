import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
import requests
from sqlalchemy.orm import Session

from .models import AuditLog, Match, Prediction
from .sync import translate_team_name
from .scoring import (
    score_prediction, load_stage_multipliers, invalidate_ranking_cache,
    capture_ranking_snapshot, capture_ranking_update_snapshot
)
from .notifications import send_general_ranking_notification

logger = logging.getLogger("fifa_live_sync")

def _extract_desc(v) -> str | None:
    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
        return v[0].get("Description")
    return None

def _normalize(value: str | None) -> str:
    if not value:
        return ""
    value = translate_team_name(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _teams_match(api_team_name: str, local_team_name: str, local_fifa_code: str | None = None) -> bool:
    local_candidates = {_normalize(local_team_name)}
    if local_fifa_code:
        local_candidates.add(_normalize(local_fifa_code))

    api_candidates = {_normalize(api_team_name)}
    return bool(local_candidates.intersection(api_candidates))

def fetch_fifa_matches() -> list[dict]:
    url = "https://api.fifa.com/api/v3/calendar/matches?idCompetition=17&idSeason=285023&count=300&language=en"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
        return payload.get("Results") or []
    except Exception as e:
        logger.error(f"Erro ao baixar dados da FIFA API: {str(e)}")
        return []

def find_local_match(api_match: dict, db_matches: list[Match]) -> Match | None:
    api_date_str = api_match.get("Date")
    if not api_date_str:
        return None
    try:
        api_kickoff = datetime.fromisoformat(api_date_str.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None

    home_node = api_match.get("Home") or {}
    away_node = api_match.get("Away") or {}
    
    api_home_name = _extract_desc(home_node.get("TeamName")) or home_node.get("ShortClubName") or home_node.get("Abbreviation")
    api_away_name = _extract_desc(away_node.get("TeamName")) or away_node.get("ShortClubName") or away_node.get("Abbreviation")

    if not api_home_name or not api_away_name:
        return None

    for m in db_matches:
        if abs(m.kickoff_time - api_kickoff) > timedelta(minutes=20):
            continue
        
        home_code = getattr(m.team1, "fifa_code", None)
        away_code = getattr(m.team2, "fifa_code", None)
        
        if _teams_match(api_home_name, m.team1_name, home_code) and _teams_match(api_away_name, m.team2_name, away_code):
            return m
            
    return None

def sync_fifa_scores_and_live(db: Session) -> dict:
    """
    Main job that polls FIFA API.
    Updates live matches individually.
    Updates finished matches in kickoff groups if they did not go to extra time/penalties.
    """
    results = {"live_updates": 0, "finished_updates": 0, "skipped_extra_time": 0}
    
    # Check if there are active or upcoming matches starting soon to sync
    now = datetime.utcnow()
    active_or_upcoming = db.query(Match).filter(
        Match.status.notin_(["postponed", "cancelled", "score_confirmed", "finished"]),
        Match.kickoff_time <= now + timedelta(minutes=20)
    ).first()
    
    if not active_or_upcoming:
        return results
        
    api_matches = fetch_fifa_matches()
    if not api_matches:
        return results

    # Get all active/non-confirmed local matches
    db_matches = db.query(Match).filter(
        Match.status.notin_(["postponed", "cancelled", "score_confirmed"])
    ).all()

    # 1. Update individual live matches first
    for api_match in api_matches:
        status_code = api_match.get("MatchStatus")
        if status_code == 3:  # Live
            local_match = find_local_match(api_match, db_matches)
            if local_match and local_match.status != "score_confirmed":
                home_score = api_match.get("HomeTeamScore")
                away_score = api_match.get("AwayTeamScore")
                match_time = api_match.get("MatchTime") or "0'"
                
                if (local_match.score_ft_team1 != home_score or 
                    local_match.score_ft_team2 != away_score or 
                    local_match.status != "live" or 
                    local_match.live_minute != match_time):
                    
                    local_match.status = "live"
                    local_match.score_ft_team1 = home_score
                    local_match.score_ft_team2 = away_score
                    local_match.live_minute = match_time
                    db.commit()
                    results["live_updates"] += 1
                    logger.info(f"Partida {local_match.team1_name} x {local_match.team2_name} atualizada para AO VIVO ({match_time}) - Placar: {home_score} x {away_score}")

    # Re-fetch local matches that are not finished
    pending_matches = db.query(Match).filter(
        Match.status.notin_(["postponed", "cancelled", "score_confirmed", "finished"]),
        Match.score_confirmed_by_admin == False
    ).all()

    if not pending_matches:
        return results

    # Group pending local matches by kickoff time
    kickoff_groups = {}
    for m in pending_matches:
        kickoff_groups.setdefault(m.kickoff_time, []).append(m)

    # 2. Process finished matches in kickoff groups
    for kickoff_time, group_matches in kickoff_groups.items():
        # Match all group matches to FIFA API finished matches
        matched_api_matches = {}
        all_finished = True
        has_extra_time = False

        for match in group_matches:
            found_api = None
            for api_m in api_matches:
                # Must be finished (MatchStatus == 0)
                if api_m.get("MatchStatus") == 0:
                    lm = find_local_match(api_m, [match])
                    if lm:
                        found_api = api_m
                        break
            
            if not found_api:
                all_finished = False
                break
            
            matched_api_matches[match.id] = found_api
            # Check for extra time/penalties (ResultType 2 = penalty shootout, 3 = extra time decision)
            if found_api.get("ResultType") in [2, 3]:
                has_extra_time = True

        if not all_finished:
            # Not all matches at this kickoff time are finished in the FIFA API yet
            continue

        if has_extra_time:
            # At least one match went to extra time. Skip FIFA sync for this group
            # and let football-data.org (or admin) handle it as a fallback.
            results["skipped_extra_time"] += len(group_matches)
            logger.info(f"Grupo de kickoff {kickoff_time.isoformat()} ignorado na FIFA API porque contém jogo com prorrogação. Fallback ativado.")
            continue

        # Apply finished scores for all matches in the kickoff group
        stage_multipliers = load_stage_multipliers(db)
        logger.info(f"Aplicando placares finais da FIFA API para o horário {kickoff_time.isoformat()} ({len(group_matches)} jogos)...")
        
        for match in group_matches:
            api_match = matched_api_matches[match.id]
            home_score = api_match.get("HomeTeamScore")
            away_score = api_match.get("AwayTeamScore")

            old_value = {
                "score_ft_team1": match.score_ft_team1,
                "score_ft_team2": match.score_ft_team2,
                "status": match.status,
            }

            match.score_ft_team1 = home_score
            match.score_ft_team2 = away_score
            match.score_et_team1 = None
            match.score_et_team2 = None
            match.score_pen_team1 = None
            match.score_pen_team2 = None
            match.status = "finished"
            match.live_minute = None
            match.score_confirmed_by_admin = False
            
            db.flush()

            db.add(AuditLog(
                user_id=None,
                action="fifa_api_score_auto_update",
                target_type="match",
                target_id=str(match.id),
                old_value=old_value,
                new_value={
                    "score_ft_team1": match.score_ft_team1,
                    "score_ft_team2": match.score_ft_team2,
                    "status": match.status,
                },
                reason="Resultado final automático via FIFA API",
            ))

            # Score predictions
            predictions = db.query(Prediction).filter(Prediction.match_id == match.id).all()
            for prediction in predictions:
                score_prediction(db, prediction, match, stage_multipliers)

        db.commit()
        invalidate_ranking_cache(db)
        capture_ranking_snapshot(db)
        capture_ranking_update_snapshot(db, kickoff_time=kickoff_time)
        send_general_ranking_notification(db)
        results["finished_updates"] += len(group_matches)
        logger.info(f"Placares finais aplicados e rankings atualizados para {kickoff_time.isoformat()}.")

    return results
