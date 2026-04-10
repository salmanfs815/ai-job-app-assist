from app.models.schemas import RewriteBullet


def compute_match_score(matched: list[str], missing: list[str], keywords: list[str]) -> int:
    if not keywords:
        return 0

    coverage = len(set(matched)) / max(1, len(set(keywords)))
    penalty = len(set(missing)) / max(1, len(set(keywords)))
    raw = (coverage * 100) - (penalty * 20)
    return max(0, min(100, int(round(raw))))


def build_suggestions(missing_skills: list[str], bullets: list[RewriteBullet]) -> list[str]:
    out: list[str] = []

    if missing_skills:
        out.append("Add evidence for: " + ", ".join(missing_skills[:5]))

    for bullet in bullets[:3]:
        out.append(f"Use impact-focused wording: {bullet.tailored}")

    return out
