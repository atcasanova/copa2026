from decimal import Decimal
from sqlalchemy.orm import Session
from .models import (
    Match, Prediction, User, StageMultiplier, AuditLog, RankingCache,
    RankingSnapshot, RankingUpdateSnapshot
)
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

# Default multipliers as positive floats
DEFAULT_MULTIPLIERS = {
    "Group Stage": 1.0,
    "Round of 32": 2.0,
    "Round of 16": 3.0,
    "Quarter-finals": 4.0,
    "Semi-finals": 5.0,
    "Final": 6.0
}

LOCAL_TIMEZONE = ZoneInfo("America/Sao_Paulo")
RANKING_FINAL_STATUSES = ["finished", "score_confirmed", "score_pending_review"]

def load_stage_multipliers(db: Session) -> dict[str, Decimal]:
    return {multiplier.stage: multiplier.multiplier for multiplier in db.query(StageMultiplier).all()}


def get_stage_multiplier(db: Session, stage: str, stage_multipliers: dict[str, Decimal] | None = None) -> Decimal:
    """
    Fetch the multiplier for a stage. Fallback to default if not present.
    """
    if stage_multipliers is not None and stage in stage_multipliers:
        return stage_multipliers[stage]
    db_multiplier = db.query(StageMultiplier).filter(StageMultiplier.stage == stage).first()
    if db_multiplier:
        return db_multiplier.multiplier
    return Decimal(str(DEFAULT_MULTIPLIERS.get(stage, 1.0)))

def calculate_base_points(
    pred_goals1: int, pred_goals2: int, pred_qualifier: str,
    act_goals1: int, act_goals2: int, act_qualifier: str,
    is_knockout: bool
) -> tuple[int, str]:
    """
    Scoring system rules (PT-BR explanations):
    - Exact score: 10 pts
    - Correct result and goals difference (not exact): 6 pts
    - Correct result + one team goals: 4 pts
    - Correct result only: 3 pts
    - Wrong result: 0 pts
    """
    # Determine actual and predicted results
    if act_goals1 > act_goals2:
        act_result = "team1"
    elif act_goals1 < act_goals2:
        act_result = "team2"
    else:
        act_result = "draw"

    if pred_goals1 > pred_goals2:
        pred_result = "team1"
    elif pred_goals1 < pred_goals2:
        pred_result = "team2"
    else:
        pred_result = "draw"

    # Check if result is correct
    if act_result == pred_result:
        # Exact score check
        if act_goals1 == pred_goals1 and act_goals2 == pred_goals2:
            return 10, "Placar exato (10 pontos)"
        
        # Correct result and goals difference (not exact)
        act_diff = act_goals1 - act_goals2
        pred_diff = pred_goals1 - pred_goals2
        if act_diff == pred_diff:
            return 6, "Resultado correto e diferença de gols (6 pontos)"
            
        # Correct result + one team goals
        if act_goals1 == pred_goals1 or act_goals2 == pred_goals2:
            return 4, "Resultado correto + gols de um dos times (4 pontos)"
            
        # Correct result only
        return 3, "Resultado correto (3 pontos)"
    else:
        return 0, "Resultado incorreto (0 pontos)"

def score_prediction(
    db: Session,
    prediction: Prediction,
    match: Match,
    stage_multipliers: dict[str, Decimal] | None = None
) -> None:
    """
    Calculate and save score for a single prediction.
    """
    # 1. Determine official score for prediction purposes (tempo regulamentar - full time score)
    if match.score_ft_team1 is not None and match.score_ft_team2 is not None:
        act_goals1 = match.score_ft_team1
        act_goals2 = match.score_ft_team2
    else:
        # Match is not finished/scored yet
        prediction.points_earned = None
        prediction.base_points = None
        prediction.multiplier_used = None
        prediction.scoring_explanation = None
        return

    is_knockout = match.stage != "Group Stage"
    
    # 2. Determine who qualified officially in knockout
    act_qualifier = None
    if is_knockout:
        if act_goals1 > act_goals2:
            act_qualifier = match.team1_name
        elif act_goals1 < act_goals2:
            act_qualifier = match.team2_name
        else:
            # Full time was a draw, check extra time
            if match.score_et_team1 is not None and match.score_et_team2 is not None:
                if match.score_et_team1 > match.score_et_team2:
                    act_qualifier = match.team1_name
                elif match.score_et_team1 < match.score_et_team2:
                    act_qualifier = match.team2_name
                else:
                    # Extra time was a draw, check penalties
                    if match.score_pen_team1 is not None and match.score_pen_team2 is not None:
                        if match.score_pen_team1 > match.score_pen_team2:
                            act_qualifier = match.team1_name
                        else:
                            act_qualifier = match.team2_name
            else:
                # If extra time scores are not filled, check penalties directly
                if match.score_pen_team1 is not None and match.score_pen_team2 is not None:
                    if match.score_pen_team1 > match.score_pen_team2:
                        act_qualifier = match.team1_name
                    else:
                        act_qualifier = match.team2_name

    # 3. Calculate base points
    base_pts, explanation = calculate_base_points(
        prediction.goals_team1, prediction.goals_team2, prediction.qualified_team_name,
        act_goals1, act_goals2, act_qualifier,
        is_knockout
    )

    # 4. Apply stage multiplier
    multiplier = get_stage_multiplier(db, match.stage, stage_multipliers)
    final_pts = int(base_pts * float(multiplier))

    # Optional check: If qualifier prediction is configurable to add points in the future, we could add here.
    # Currently, default is 0 additional points for correct qualified team prediction, but we store user prediction.
    
    # 5. Save details
    prediction.base_points = base_pts
    prediction.multiplier_used = multiplier
    prediction.points_earned = final_pts
    
    stage_pt = match.stage
    if stage_pt == "Group Stage":
        stage_pt = "Fase de Grupos"
    elif stage_pt == "Round of 32":
        stage_pt = "Dezesseis-avos"
    elif stage_pt == "Round of 16":
        stage_pt = "Oitavas de Final"
    elif stage_pt == "Quarter-finals":
        stage_pt = "Quartas de Final"
    elif stage_pt == "Semi-finals":
        stage_pt = "Semifinal"
    elif stage_pt == "Final":
        stage_pt = "Final"

    prediction.scoring_explanation = f"{explanation} x Multiplicador {multiplier}x ({stage_pt})"

def invalidate_ranking_cache(db: Session) -> None:
    """
    Deletes all cached ranking data.
    """
    try:
        db.query(RankingCache).delete()
        db.commit()
    except Exception:
        db.rollback()

def serialize_ranking_row(row: dict) -> dict:
    return {
        "user_id": str(row["user_id"]),
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "total_points": row["total_points"],
        "exact_scores_count": row["exact_scores_count"],
        "correct_results_count": row["correct_results_count"],
        "knockout_points": row["knockout_points"],
        "predictions_count": row["predictions_count"],
        "missing_predictions_count": row["missing_predictions_count"],
        "registration_date": row["registration_date"].isoformat() if isinstance(row["registration_date"], datetime) else row["registration_date"],
        "position": row["position"],
        "previous_position": row.get("previous_position"),
        "position_change": row.get("position_change")
    }


def is_kickoff_group_rankable(db: Session, kickoff_time: datetime) -> bool:
    matches = db.query(Match).filter(
        Match.kickoff_time == kickoff_time,
        Match.status.notin_(["postponed", "cancelled"])
    ).all()
    if not matches:
        return False
    return all(
        match.status in RANKING_FINAL_STATUSES
        and match.score_ft_team1 is not None
        and match.score_ft_team2 is not None
        for match in matches
    )


def should_publish_ranking_update_for_matches(db: Session, matches: list[Match]) -> bool:
    return any(is_kickoff_group_rankable(db, match.kickoff_time) for match in matches)


def get_rankable_match_ids(db: Session, stage: str = None, date_str: str = None) -> set[int]:
    query = db.query(Match).filter(
        Match.status.in_(RANKING_FINAL_STATUSES),
        Match.score_ft_team1 != None,
        Match.score_ft_team2 != None
    )
    if stage:
        query = query.filter(Match.stage == stage)
    if date_str:
        query = query.filter(Match.date == date_str)

    candidates = query.all()
    rankable_kickoffs = {
        match.kickoff_time
        for match in candidates
        if is_kickoff_group_rankable(db, match.kickoff_time)
    }
    return {match.id for match in candidates if match.kickoff_time in rankable_kickoffs}


def _latest_ranking_update_rows(db: Session) -> dict[str, RankingUpdateSnapshot]:
    latest_key = db.query(RankingUpdateSnapshot.update_key).order_by(
        RankingUpdateSnapshot.created_at.desc(),
        RankingUpdateSnapshot.update_key.desc()
    ).limit(1).scalar()
    if not latest_key:
        return {}
    rows = db.query(RankingUpdateSnapshot).filter(RankingUpdateSnapshot.update_key == latest_key).all()
    return {str(row.user_id): row for row in rows}


def enrich_ranking_with_position_changes(db: Session, ranking: list[dict]) -> list[dict]:
    latest_rows = _latest_ranking_update_rows(db)
    enriched = []
    for row in ranking:
        next_row = dict(row)
        snapshot = latest_rows.get(str(row["user_id"]))
        if (
            snapshot
            and snapshot.position == row["position"]
            and snapshot.total_points == row["total_points"]
        ):
            next_row["previous_position"] = snapshot.previous_position
            next_row["position_change"] = snapshot.position_change
        else:
            next_row["previous_position"] = None
            next_row["position_change"] = None
        enriched.append(next_row)
    return enriched

def recalculate_match_predictions(db: Session, match_id: int) -> None:
    """
    Recalculate points for all predictions of a single match.
    """
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        return
        
    stage_multipliers = load_stage_multipliers(db)
    predictions = db.query(Prediction).filter(Prediction.match_id == match_id).all()
    for pred in predictions:
        score_prediction(db, pred, match, stage_multipliers)
    db.commit()
    invalidate_ranking_cache(db)

def recalculate_all_predictions_and_rankings(db: Session) -> None:
    """
    Recalculates all predictions in the entire database.
    Useful after multiplier changes or administrative reset.
    """
    stage_multipliers = load_stage_multipliers(db)
    matches = db.query(Match).filter(Match.status.in_(["finished", "score_confirmed"])).all()
    for match in matches:
        predictions = db.query(Prediction).filter(Prediction.match_id == match.id).all()
        for pred in predictions:
            score_prediction(db, pred, match, stage_multipliers)
    db.commit()
    invalidate_ranking_cache(db)

def get_rankings(db: Session, group_id: str = None, stage: str = None, date_str: str = None) -> list[dict]:
    # Determine cache key
    if group_id:
        cache_key = f"group_{group_id}"
    elif stage:
        cache_key = f"stage_{stage}"
    elif date_str:
        cache_key = f"date_{date_str}"
    else:
        cache_key = "general"

    # Serve from cache if available
    try:
        cached = db.query(RankingCache).filter(RankingCache.key == cache_key).first()
        if cached:
            return enrich_ranking_with_position_changes(db, cached.data) if cache_key == "general" else cached.data
    except Exception:
        pass
    """
    Computes ranking data based on the configured tie-breakers:
    1. highest total points;
    2. highest number of exact score predictions;
    3. highest number of correct result predictions;
    4. highest number of points in knockout stages;
    5. lowest number of missing predictions;
    6. earliest registration date;
    7. alphabetical display name order.
    """
    ranked_match_ids = get_rankable_match_ids(db, stage=stage, date_str=date_str)
    total_ranked_matches = len(ranked_match_ids)

    # 2. Base query for users
    users_query = db.query(User).filter(
        User.is_active == True,
        User.role.notin_(["system_admin", "score_admin"]),
        User.payment_status == "approved"
    )
    if group_id:
        from .models import GroupMember
        users_query = users_query.join(GroupMember, GroupMember.user_id == User.id)\
                                 .filter(GroupMember.group_id == group_id, GroupMember.is_approved == True)

    users = users_query.all()
    ranking_list = []

    for user in users:
        # Base query for user predictions
        pred_query = db.query(Prediction).join(Match, Match.id == Prediction.match_id)\
                                         .filter(Prediction.user_id == user.id)
        
        # Apply filters if present
        if stage:
            pred_query = pred_query.filter(Match.stage == stage)
        if date_str:
            pred_query = pred_query.filter(Match.date == date_str)

        predictions = pred_query.all()

        total_points = 0
        exact_scores = 0
        correct_results = 0
        knockout_points = 0
        predictions_made = len(predictions)

        for pred in predictions:
            if pred.match_id not in ranked_match_ids:
                continue
            if pred.points_earned is not None:
                total_points += pred.points_earned
                # Check base points to identify exact vs correct results
                if pred.base_points == 10:
                    exact_scores += 1
                    correct_results += 1
                elif pred.base_points in [3, 4, 6]:
                    correct_results += 1
                
                # Check if it is a knockout stage match
                # Stage choices are Group Stage, Round of 32, Round of 16, etc.
                if pred.match.stage != "Group Stage":
                    knockout_points += pred.points_earned

        ranked_prediction_count = sum(1 for pred in predictions if pred.match_id in ranked_match_ids)
        missing_predictions = max(0, total_ranked_matches - ranked_prediction_count)

        ranking_list.append({
            "user_id": user.id,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "total_points": total_points,
            "exact_scores_count": exact_scores,
            "correct_results_count": correct_results,
            "knockout_points": knockout_points,
            "predictions_count": predictions_made,
            "missing_predictions_count": missing_predictions,
            "registration_date": user.created_at
        })

    # Tie-breaker sorting function key
    # Criteria:
    # 1. total_points (DESC) -> -total_points
    # 2. exact_scores_count (DESC) -> -exact_scores_count
    # 3. correct_results_count (DESC) -> -correct_results_count
    # 4. knockout_points (DESC) -> -knockout_points
    # 5. missing_predictions_count (ASC) -> missing_predictions_count
    # 6. registration_date (ASC) -> registration_date timestamp
    # 7. display_name (ASC) -> display_name.lower()
    def sort_key(row):
        return (
            -row["total_points"],
            -row["exact_scores_count"],
            -row["correct_results_count"],
            -row["knockout_points"],
            row["missing_predictions_count"],
            row["registration_date"].timestamp(),
            row["display_name"].lower()
        )

    ranking_list.sort(key=sort_key)

    # Assign positions (handling ties: same stats get same position)
    current_pos = 1
    for idx, row in enumerate(ranking_list):
        if idx > 0:
            prev = ranking_list[idx - 1]
            # Check if tied on all sorting metrics except registration date and alphabetical name
            is_tied = (
                row["total_points"] == prev["total_points"] and
                row["exact_scores_count"] == prev["exact_scores_count"] and
                row["correct_results_count"] == prev["correct_results_count"] and
                row["knockout_points"] == prev["knockout_points"] and
                row["missing_predictions_count"] == prev["missing_predictions_count"]
            )
            if not is_tied:
                current_pos = idx + 1
        row["position"] = current_pos

    # Save to cache before returning
    try:
        serialized = [serialize_ranking_row(row) for row in ranking_list]
        cache_entry = db.query(RankingCache).filter(RankingCache.key == cache_key).first()
        if not cache_entry:
            cache_entry = RankingCache(key=cache_key, data=serialized)
            db.add(cache_entry)
        else:
            cache_entry.data = serialized
            cache_entry.updated_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()

    return enrich_ranking_with_position_changes(db, ranking_list) if cache_key == "general" else ranking_list


def capture_ranking_snapshot(db: Session, snapshot_date=None) -> int:
    if snapshot_date is None:
        snapshot_date = datetime.now(LOCAL_TIMEZONE).date()

    ranking = get_rankings(db)
    db.query(RankingSnapshot).filter(RankingSnapshot.snapshot_date == snapshot_date).delete(synchronize_session=False)

    for row in ranking:
        db.add(RankingSnapshot(
            snapshot_date=snapshot_date,
            user_id=row["user_id"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            position=row["position"],
            total_points=row["total_points"],
            exact_scores_count=row["exact_scores_count"],
            correct_results_count=row["correct_results_count"],
        ))

    db.commit()
    return len(ranking)


def capture_ranking_update_snapshot(db: Session, kickoff_time: datetime | None = None) -> int:
    ranking = get_rankings(db)
    previous_rows = _latest_ranking_update_rows(db)
    update_key = datetime.utcnow().isoformat(timespec="microseconds")

    for row in ranking:
        previous = previous_rows.get(str(row["user_id"]))
        previous_position = previous.position if previous else None
        position_change = previous_position - row["position"] if previous_position is not None else None
        user_id = UUID(row["user_id"]) if isinstance(row["user_id"], str) else row["user_id"]
        db.add(RankingUpdateSnapshot(
            update_key=update_key,
            kickoff_time=kickoff_time,
            user_id=user_id,
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            position=row["position"],
            previous_position=previous_position,
            position_change=position_change,
            total_points=row["total_points"],
            exact_scores_count=row["exact_scores_count"],
            correct_results_count=row["correct_results_count"],
        ))

    db.commit()
    invalidate_ranking_cache(db)
    return len(ranking)

def map_round_to_stage(round_str: str) -> str:
    """
    Maps round names to tournament stages.
    """
    r = round_str.lower()
    if "matchday" in r:
        return "Group Stage"
    elif "32" in r or "thirty-two" in r:
        return "Round of 32"
    elif "16" in r or "sixteen" in r:
        return "Round of 16"
    elif "quarter" in r:
        return "Quarter-finals"
    elif "semi" in r:
        return "Semi-finals"
    elif "final" in r or "third" in r:
        return "Final"
    return "Group Stage"
