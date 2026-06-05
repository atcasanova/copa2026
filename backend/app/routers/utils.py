import unicodedata
from typing import List
from sqlalchemy.orm import Session
from ..models import Match, User

def normalized_text_sort_key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()

def user_name_sort_key(user: User) -> tuple[str, str, str]:
    return (
        normalized_text_sort_key(user.display_name),
        normalized_text_sort_key(user.username),
        normalized_text_sort_key(user.email),
    )

def get_unlocked_stages(db: Session) -> List[str]:
    """
    Dynamically calculates which stages are unlocked based on completion of previous stages.
    "Group Stage" is always unlocked.
    A stage is unlocked if all matches in the previous stage are finished/confirmed.
    """
    stages_order = ["Group Stage", "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final"]
    unlocked = ["Group Stage"]
    
    for i in range(len(stages_order) - 1):
        prev_stage = stages_order[i]
        next_stage = stages_order[i+1]
        
        # Check if there are any matches in the database for the previous stage
        prev_matches = db.query(Match).filter(Match.stage == prev_stage).all()
        if not prev_matches:
            # If the database does not contain matches for the previous stage yet, stop unlocking
            break
            
        # Check if all matches in the previous stage are completed
        all_finished = all(m.status in ["finished", "score_confirmed"] for m in prev_matches)
        if all_finished:
            unlocked.append(next_stage)
        else:
            break
            
    return unlocked
