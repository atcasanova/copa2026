import os
import requests
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from .models import Team, Stadium, Match, SyncLog, SyncMatchDiff, AuditLog
from .db import SessionLocal
from .scoring import recalculate_match_predictions, map_round_to_stage
from .settings import is_match_locked_for_predictions

TEAMS_URL = os.getenv("TEAMS_JSON_URL", "https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.teams.json")
STADIUMS_URL = os.getenv("STADIUMS_JSON_URL", "https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.stadiums.json")
MATCHES_URL = os.getenv("MATCHES_JSON_URL", "https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.json")

TEAM_TRANSLATIONS = {
    'Mexico': 'México',
    'South Africa': 'África do Sul',
    'South Korea': 'Coreia do Sul',
    'Czech Republic': 'República Tcheca',
    'Canada': 'Canadá',
    'Bosnia & Herzegovina': 'Bósnia e Herzegovina',
    'Qatar': 'Catar',
    'Switzerland': 'Suíça',
    'Brazil': 'Brasil',
    'Morocco': 'Marrocos',
    'Haiti': 'Haiti',
    'Scotland': 'Escócia',
    'USA': 'Estados Unidos',
    'Paraguay': 'Paraguai',
    'Australia': 'Austrália',
    'Turkey': 'Turquia',
    'Germany': 'Alemanha',
    'Curaçao': 'Curaçao',
    'Ivory Coast': 'Costa do Marfim',
    'Ecuador': 'Equador',
    'Netherlands': 'Holanda',
    'Japan': 'Japão',
    'Sweden': 'Suécia',
    'Tunisia': 'Tunísia',
    'Belgium': 'Bélgica',
    'Egypt': 'Egito',
    'Iran': 'Irã',
    'New Zealand': 'Nova Zelândia',
    'Spain': 'Espanha',
    'Cape Verde': 'Cabo Verde',
    'Saudi Arabia': 'Arábia Saudita',
    'Uruguay': 'Uruguai',
    'France': 'França',
    'Senegal': 'Senegal',
    'Iraq': 'Iraque',
    'Norway': 'Noruega',
    'Argentina': 'Argentina',
    'Algeria': 'Argélia',
    'Austria': 'Áustria',
    'Jordan': 'Jordânia',
    'Portugal': 'Portugal',
    'DR Congo': 'RD Congo',
    'Uzbekistan': 'Uzbequistão',
    'Colombia': 'Colômbia',
    'England': 'Inglaterra',
    'Croatia': 'Croácia',
    'Ghana': 'Gana',
    'Panama': 'Panamá',
}

def translate_team_name(name: str) -> str:
    if not name:
        return name
    if name in TEAM_TRANSLATIONS:
        return TEAM_TRANSLATIONS[name]
    
    # Handle knockout phase placeholder names
    name = re.sub(r"Winner Group\s+([A-L])", r"Vencedor do Grupo \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Runner-up Group\s+([A-L])", r"Segundo do Grupo \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Winner Match\s+(\d+)", r"Vencedor do Jogo \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Runner-up Match\s+(\d+)", r"Segundo do Jogo \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Winner Group Stage Match\s+(\d+)", r"Vencedor do Jogo \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Runner-up Group Stage Match\s+(\d+)", r"Segundo do Jogo \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Winner RD32_(\d+)", r"Vencedor R32 \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Winner R16_(\d+)", r"Vencedor Oitavas \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Winner QF_(\d+)", r"Vencedor Quartas \1", name, flags=re.IGNORECASE)
    name = re.sub(r"Winner SF_(\d+)", r"Vencedor Semifinal \1", name, flags=re.IGNORECASE)
    return name

def translate_round_name(round_name: str) -> str:
    if not round_name:
        return round_name
    round_name = re.sub(r"Matchday\s+(\d+)", r"Dia \1", round_name, flags=re.IGNORECASE)
    if round_name.lower() == "round of 32":
        return "Dezesseis-avos de Final"
    elif round_name.lower() == "round of 16":
        return "Oitavas de Final"
    elif round_name.lower() in ["quarter-final", "quarter-finals"]:
        return "Quartas de Final"
    elif round_name.lower() in ["semi-final", "semi-finals"]:
        return "Semifinal"
    elif round_name.lower() == "match for third place":
        return "Disputa do Terceiro Lugar"
    elif round_name.lower() == "final":
        return "Final"
    return round_name

def translate_group_name(group_name: str) -> str:
    if not group_name:
        return group_name
    return re.sub(r"Group\s+([A-L])", r"Grupo \1", group_name, flags=re.IGNORECASE)

def parse_kickoff_to_utc(date_str: str, time_str: str) -> datetime:
    """
    Parses date and time string from openfootball into a UTC datetime.
    Example: date="2026-06-11", time="13:00 UTC-6"
    """
    time_str = time_str.strip()
    # Match time part: HH:MM
    time_match = re.match(r"^(\d{2}):(\d{2})", time_str)
    if not time_match:
        # Fallback to midnight UTC
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)
        
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    
    local_dt = datetime.strptime(f"{date_str} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
    
    # Check for UTC offset, e.g. "UTC-6", "UTC+5", "UTC-07"
    offset_match = re.search(r"UTC([+-]?\d+)", time_str)
    if offset_match:
        offset_hours = int(offset_match.group(1))
        # UTC_time = Local_time - offset
        utc_dt = local_dt - timedelta(hours=offset_hours)
        return utc_dt
    else:
        # Fallback: assume UTC
        return local_dt

def ensure_team_exists(db: Session, team_name: str) -> Team:
    """
    Ensures a team exists in the database. If not, inserts it as a placeholder.
    Helps maintain foreign key constraints for knockout placeholders (e.g., "Winner Group A").
    """
    translated_name = translate_team_name(team_name)
    team = db.query(Team).filter(Team.name == translated_name).first()
    if not team:
        # Check if the name corresponds to a placeholder team (e.g. 1A, 2B, or Winner Group A)
        is_placeholder = any(kw in translated_name.lower() for kw in ["vencedor", "segundo", "grupo", "jogo", "r32", "oitavas", "quartas", "semifinal", "winner", "runner", "match", "placeholder"]) or len(translated_name) < 3
        fifa_code = None if is_placeholder else translated_name[:3].upper()
        if fifa_code:
            existing_code = db.query(Team).filter(Team.fifa_code == fifa_code).first()
            if existing_code:
                fifa_code = None
        
        team = Team(
            name=translated_name,
            fifa_code=fifa_code,
            group_name="Knockout Placeholder",
            continent="Desconhecido",
            flag_icon="🏳️"
        )
        db.add(team)
        db.commit()
        db.refresh(team)
    return team

def ensure_stadium_exists(db: Session, stadium_name: str) -> Stadium:
    """
    Ensures a stadium exists in the database. If not, inserts a fallback placeholder.
    """
    stadium = db.query(Stadium).filter(Stadium.name == stadium_name).first()
    if not stadium:
        stadium = Stadium(
            name=stadium_name,
            city="Desconhecida",
            capacity=40000,
            timezone="UTC"
        )
        db.add(stadium)
        db.commit()
        db.refresh(stadium)
    return stadium

def seed_initial_data(db: Session) -> dict:
    """
    Fetches and seeds teams, stadiums, and matches.
    """
    results = {"teams": 0, "stadiums": 0, "matches": 0, "errors": []}
    
    # 1. Seed Teams
    try:
        r = requests.get(TEAMS_URL, timeout=15)
        if r.status_code == 200:
            teams_data = r.json()
            for t in teams_data:
                translated_name = translate_team_name(t["name"])
                existing = db.query(Team).filter(Team.name == translated_name).first()
                if not existing:
                    team = Team(
                        name=translated_name,
                        fifa_code=t.get("fifa_code") or t.get("name_normalised", translated_name)[:3].upper(),
                        group_name=translate_group_name(t.get("group")) or "Placeholder",
                        continent=t.get("continent"),
                        flag_icon=t.get("flag_icon") or "🏳️",
                        confed=t.get("confed")
                    )
                    db.add(team)
                    results["teams"] += 1
            db.commit()
    except Exception as e:
        results["errors"].append(f"Erro ao importar times: {str(e)}")

    # 2. Seed Stadiums
    try:
        r = requests.get(STADIUMS_URL, timeout=15)
        if r.status_code == 200:
            stadiums_data = r.json().get("stadiums", [])
            for s in stadiums_data:
                existing = db.query(Stadium).filter(Stadium.name == s["name"]).first()
                if not existing:
                    stadium = Stadium(
                        name=s["name"],
                        city=s.get("city") or "Desconhecida",
                        capacity=s.get("capacity"),
                        timezone=s.get("timezone") or "UTC",
                        coords=s.get("coords")
                    )
                    db.add(stadium)
                    results["stadiums"] += 1
            db.commit()
    except Exception as e:
        results["errors"].append(f"Erro ao importar estádios: {str(e)}")

    # 3. Seed Matches
    try:
        r = requests.get(MATCHES_URL, timeout=15)
        if r.status_code == 200:
            payload = r.json()
            matches_data = payload.get("matches", [])
            for m in matches_data:
                # Ensure teams & stadium exist (foreign keys)
                team1_translated = translate_team_name(m["team1"])
                team2_translated = translate_team_name(m["team2"])
                ensure_team_exists(db, team1_translated)
                ensure_team_exists(db, team2_translated)
                ensure_stadium_exists(db, m["ground"])

                kickoff = parse_kickoff_to_utc(m["date"], m["time"])
                stage = map_round_to_stage(m["round"])
                round_translated = translate_round_name(m["round"])
                group_translated = translate_group_name(m.get("group"))
                
                # Check if match already exists
                existing = db.query(Match).filter(
                    Match.round == round_translated,
                    Match.team1_name == team1_translated,
                    Match.team2_name == team2_translated
                ).first()

                if not existing:
                    match = Match(
                        round=round_translated,
                        stage=stage,
                        group_name=group_translated,
                        date=m["date"],
                        time_str=m["time"],
                        kickoff_time=kickoff,
                        team1_name=team1_translated,
                        team2_name=team2_translated,
                        ground=m["ground"],
                        status="scheduled"
                    )
                    
                    # If score is present in seed data (unlikely for 2026, but useful for reference/tests)
                    if "score" in m:
                        score = m["score"]
                        if "ft" in score:
                            match.score_ft_team1 = score["ft"][0]
                            match.score_ft_team2 = score["ft"][1]
                            match.status = "finished"
                        if "et" in score:
                            match.score_et_team1 = score["et"][0]
                            match.score_et_team2 = score["et"][1]
                        if "p" in score:
                            match.score_pen_team1 = score["p"][0]
                            match.score_pen_team2 = score["p"][1]

                    db.add(match)
                    results["matches"] += 1
            db.commit()
    except Exception as e:
        results["errors"].append(f"Erro ao importar partidas: {str(e)}")
        
    return results

def sync_openfootball_data(db: Session, force_sync: bool = False) -> tuple[str, bool, dict]:
    """
    Daily sync check. Computes hash of MATCHES_URL.
    Checks for differences, registers diffs, and recalculates scores.
    Returns (status_msg, requires_review, results_dict).
    """
    requires_review = False
    details = {}
    
    try:
        r = requests.get(MATCHES_URL, timeout=15)
        if r.status_code != 200:
            return f"Erro ao acessar servidor do openfootball (HTTP {r.status_code})", False, {}
            
        raw_payload = r.text
        source_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        
        # Check if hash already exists in DB
        last_log = db.query(SyncLog).order_by(SyncLog.timestamp.desc()).first()
        if last_log and last_log.source_hash == source_hash and not force_sync:
            # Hash unchanged, log successful check without updating anything
            new_log = SyncLog(
                source_url=MATCHES_URL,
                source_hash=source_hash,
                raw_payload=raw_payload[:1000],  # store snapshot
                status="success",
                details="Sem alterações no arquivo de origem (Hash idêntico)"
            )
            db.add(new_log)
            db.commit()
            return "Sincronização concluída: nenhuma alteração detectada.", False, {"hash_changed": False}
            
        # Parse payload
        payload_data = json.loads(raw_payload)
        matches_list = payload_data.get("matches", [])
        
        # Create SyncLog record first (will link diffs)
        sync_log = SyncLog(
            source_url=MATCHES_URL,
            source_hash=source_hash,
            raw_payload=raw_payload[:5000],  # snapshot limit
            status="success",
            details="Processando alterações..."
        )
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)
        
        diff_count = 0
        recalculated_matches = 0
        
        for m in matches_list:
            kickoff = parse_kickoff_to_utc(m["date"], m["time"])
            stage = map_round_to_stage(m["round"])
            
            team1_translated = translate_team_name(m["team1"])
            team2_translated = translate_team_name(m["team2"])
            round_translated = translate_round_name(m["round"])
            group_translated = translate_group_name(m.get("group"))
            
            # Find matching record in DB (using round and original/placeholder teams)
            # Or matching by round, date, and ground since team names might change
            # Finding match by date, ground and round is more robust when teams are updated from placeholders.
            match = db.query(Match).filter(
                Match.round == round_translated,
                Match.date == m["date"],
                Match.ground == m["ground"]
            ).first()
            
            if not match:
                # Try finding by round and teams
                match = db.query(Match).filter(
                    Match.round == round_translated,
                    Match.team1_name == team1_translated,
                    Match.team2_name == team2_translated
                ).first()

            if not match:
                # If still not found, create it as a new match
                ensure_team_exists(db, team1_translated)
                ensure_team_exists(db, team2_translated)
                ensure_stadium_exists(db, m["ground"])
                
                match = Match(
                    round=round_translated,
                    stage=stage,
                    group_name=group_translated,
                    date=m["date"],
                    time_str=m["time"],
                    kickoff_time=kickoff,
                    team1_name=team1_translated,
                    team2_name=team2_translated,
                    ground=m["ground"],
                    status="scheduled"
                )
                db.add(match)
                db.commit()
                db.refresh(match)
                
            # Compare fields
            prev_val = {
                "team1_name": match.team1_name,
                "team2_name": match.team2_name,
                "kickoff_time": match.kickoff_time.isoformat() if match.kickoff_time else None,
                "ground": match.ground,
                "score_ft_team1": match.score_ft_team1,
                "score_ft_team2": match.score_ft_team2,
                "score_et_team1": match.score_et_team1,
                "score_et_team2": match.score_et_team2,
                "score_pen_team1": match.score_pen_team1,
                "score_pen_team2": match.score_pen_team2,
                "status": match.status
            }
            
            new_val = {
                "team1_name": team1_translated,
                "team2_name": team2_translated,
                "kickoff_time": kickoff.isoformat(),
                "ground": m["ground"],
                "score_ft_team1": m.get("score", {}).get("ft", [None, None])[0],
                "score_ft_team2": m.get("score", {}).get("ft", [None, None])[1],
                "score_et_team1": m.get("score", {}).get("et", [None, None])[0],
                "score_et_team2": m.get("score", {}).get("et", [None, None])[1],
                "score_pen_team1": m.get("score", {}).get("p", [None, None])[0],
                "score_pen_team2": m.get("score", {}).get("p", [None, None])[1],
                "status": "finished" if "score" in m else match.status
            }
            
            # Check if there are any changes
            is_changed = False
            for k in prev_val.keys():
                if prev_val[k] != new_val[k]:
                    is_changed = True
                    break
                    
            if is_changed:
                diff_count += 1
                
                # Check if this change requires manual review
                now_utc = datetime.utcnow()
                is_locked = is_match_locked_for_predictions(db, match, now_utc)
                
                score_changed = (
                    prev_val["score_ft_team1"] != new_val["score_ft_team1"] or
                    prev_val["score_ft_team2"] != new_val["score_ft_team2"] or
                    prev_val["score_et_team1"] != new_val["score_et_team1"] or
                    prev_val["score_et_team2"] != new_val["score_et_team2"] or
                    prev_val["score_pen_team1"] != new_val["score_pen_team1"] or
                    prev_val["score_pen_team2"] != new_val["score_pen_team2"]
                )
                
                team_changed = (
                    prev_val["team1_name"] != new_val["team1_name"] or
                    prev_val["team2_name"] != new_val["team2_name"]
                )
                
                kickoff_changed_near_match = False
                if prev_val["kickoff_time"] != new_val["kickoff_time"]:
                    kickoff_changed_near_match = match.kickoff_time - now_utc <= timedelta(hours=24)
                
                change_requires_review = (
                    match.score_confirmed_by_admin or
                    is_locked or
                    score_changed or
                    team_changed or
                    kickoff_changed_near_match
                )
                
                if change_requires_review:
                    requires_review = True
                    # Record diff without applying it
                    diff_record = SyncMatchDiff(
                        sync_log_id=sync_log.id,
                        match_id=match.id,
                        previous_value=prev_val,
                        new_value=new_val,
                        status="pending_review"
                    )
                    db.add(diff_record)
                else:
                    # Apply changes automatically
                    ensure_team_exists(db, team1_translated)
                    ensure_team_exists(db, team2_translated)
                    ensure_stadium_exists(db, m["ground"])
                    
                    match.team1_name = team1_translated
                    match.team2_name = team2_translated
                    match.kickoff_time = kickoff
                    match.ground = m["ground"]
                    
                    if "score" in m:
                        score = m["score"]
                        if "ft" in score:
                            match.score_ft_team1 = score["ft"][0]
                            match.score_ft_team2 = score["ft"][1]
                            match.status = "finished"
                        if "et" in score:
                            match.score_et_team1 = score["et"][0]
                            match.score_et_team2 = score["et"][1]
                        if "p" in score:
                            match.score_pen_team1 = score["p"][0]
                            match.score_pen_team2 = score["p"][1]
                    
                    db.commit()
                    
                    # Record applied diff
                    diff_record = SyncMatchDiff(
                        sync_log_id=sync_log.id,
                        match_id=match.id,
                        previous_value=prev_val,
                        new_value=new_val,
                        status="applied"
                    )
                    db.add(diff_record)
                    
                    # Create audit log
                    audit = AuditLog(
                        action="match_sync_update",
                        target_type="match",
                        target_id=str(match.id),
                        old_value=prev_val,
                        new_value=new_val,
                        reason=f"Sincronização automática do openfootball. Log #{sync_log.id}"
                    )
                    db.add(audit)
                    
                    # Recalculate predictions for this match if it has scores now
                    if match.status == "finished":
                        recalculate_match_predictions(db, match.id)
                        recalculated_matches += 1
                        
        sync_log.details = f"Sincronização concluída. Modificações encontradas: {diff_count}. Partidas recalculadas: {recalculated_matches}. Revisão manual necessária: {requires_review}"
        db.commit()
        
        return sync_log.details, requires_review, {
            "hash_changed": True,
            "diffs_found": diff_count,
            "recalculated_matches": recalculated_matches,
            "requires_review": requires_review
        }
        
    except Exception as e:
        error_msg = f"Falha na sincronização: {str(e)}"
        # Log failure
        new_log = SyncLog(
            source_url=MATCHES_URL,
            source_hash="ERROR",
            raw_payload="",
            status="failed",
            details=error_msg
        )
        db.add(new_log)
        db.commit()
        return error_msg, False, {}
