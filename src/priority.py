"""Shared deterministic priority calculation; unknown levels are not treated as low."""

LEVEL_SCORES = {"低": 1, "中": 2, "高": 3}


def priority(impact: str, urgency: str) -> tuple[int, str]:
    if impact not in LEVEL_SCORES or urgency not in LEVEL_SCORES:
        return 0, "待确认"
    score = LEVEL_SCORES[impact] * 2 + LEVEL_SCORES[urgency]
    return score, "高" if score >= 8 else "中" if score >= 5 else "低"
