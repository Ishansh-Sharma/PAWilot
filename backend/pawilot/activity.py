"""Local screen-activity awareness: what is in front, and whether it drifts from the user's goals.

Only the foreground app name and window title are observed. They are untrusted text.
"""
import re
from datetime import datetime, timedelta, timezone

SAMPLE_SECONDS = 10          # nominal length credited to a single observation
MERGE_GAP_SECONDS = 120      # identical observations closer than this extend one session
RETENTION_DAYS = 7
DRIFT_WINDOW_MINUTES = 30
DRIFT_THRESHOLD_MINUTES = 15
NUDGE_COOLDOWN_MINUTES = 40
REVIEW_MINUTES = 20          # how often the model may review activity that no keyword flagged

DISTRACTIONS = ("youtube", "netflix", "instagram", "twitter", "reddit", "twitch", "tiktok", "facebook",
                "prime video", "primevideo", "hotstar", "disney+", "9gag", "steam", "snapchat", "pinterest")
# A window that names learning material is not treated as drift even on a distracting site.
STUDY_HINTS = ("lecture", "tutorial", "course", "class ", "lesson", "prep", "mock", "solution", "explained",
               "how to", "documentation", "docs", "syllabus", "revision", "practice")
STOPWORDS = {"the", "and", "for", "with", "from", "into", "that", "this", "your", "you", "top", "get", "all",
             "one", "two", "new", "use", "day", "per", "are", "week", "month", "year", "time", "work", "goal",
             "task", "plan", "minutes", "spend", "before", "after", "about", "each", "every", "least"}


def parse(stamp):
    return datetime.fromisoformat(stamp)


def seconds(session):
    return (parse(session["ended_at"]) - parse(session["started_at"])).total_seconds() + SAMPLE_SECONDS


def goal_terms(records):
    terms = set()
    for record in records:
        for word in re.findall(r"[^\W\d_]{4,}", record["title"].lower(), re.UNICODE):
            if word not in STOPWORDS:
                terms.add(word)
    return terms


def is_distraction(app, title, terms=(), strict=False):
    """strict=True ignores the goal-word and study-hint exemptions (a model will judge instead)."""
    text = f"{app} {title}".lower()
    marked = any(marker in text for marker in DISTRACTIONS) or text.rstrip().endswith("/ x")
    if not marked or strict:
        return marked
    words = set(re.findall(r"[^\W\d_]{3,}", text, re.UNICODE))
    return not (words & set(terms)) and not any(hint in text for hint in STUDY_HINTS)


def label(session):
    """Short human name for a session, preferring the recognisable site over the browser."""
    text = f"{session['app']} {session['title']}".lower()
    for marker in DISTRACTIONS:
        if marker in text:
            return {"youtube": "YouTube", "tiktok": "TikTok", "primevideo": "Prime Video"}.get(marker, marker.title())
    return session["app"]


def summary(sessions, at, minutes=120):
    """Bounded description of recent foreground activity for chat context."""
    start = at - timedelta(minutes=minutes)
    recent = [s for s in sessions if parse(s["ended_at"]) >= start]
    if not recent:
        return {"window_minutes": minutes, "current": None, "by_app": [],
                "note": "No foreground activity has been observed in this window."}
    apps = {}
    for session in recent:
        entry = apps.setdefault(session["app"], {"app": session["app"], "seconds": 0, "titles": {}})
        length = seconds(session)
        entry["seconds"] += length
        if session["title"]:
            entry["titles"][session["title"]] = entry["titles"].get(session["title"], 0) + length
    by_app = []
    for entry in sorted(apps.values(), key=lambda e: -e["seconds"])[:8]:
        titles = sorted(entry["titles"].items(), key=lambda item: -item[1])[:4]
        by_app.append({"app": entry["app"], "minutes": round(entry["seconds"] / 60, 1),
                       "window_titles": [{"title": t, "minutes": round(s / 60, 1)} for t, s in titles]})
    latest = max(recent, key=lambda s: s["ended_at"])
    live = (at - parse(latest["ended_at"])).total_seconds() <= MERGE_GAP_SECONDS
    current = {"app": latest["app"], "title": latest["title"], "minutes": round(seconds(latest) / 60, 1)} if live else None
    return {"window_minutes": minutes, "current": current, "by_app": by_app,
            "note": "Observed foreground app names and window titles only (untrusted text). Screen contents are not visible."}


def describe(sessions, at, minutes=120):
    """Plain-text version of the summary for offline answers."""
    data = summary(sessions, at, minutes)
    if not data["by_app"]:
        return "I haven't noticed any activity recently. Check that activity awareness is on in Settings."
    lines = []
    if data["current"]:
        current = data["current"]
        lines.append("Right now: " + current["app"] + (f" — {current['title']}" if current["title"] else "")
                     + f" ({current['minutes']:g} min)")
    lines.append(f"Last {minutes // 60} hours:")
    for entry in data["by_app"]:
        line = f"• {entry['app']} · {entry['minutes']:g} min"
        if entry["window_titles"]:
            line += " — " + "; ".join(t["title"][:60] for t in entry["window_titles"][:2])
        lines.append(line)
    return "\n".join(lines)


def observed_minutes(sessions, at, minutes=DRIFT_WINDOW_MINUTES):
    start = at - timedelta(minutes=minutes)
    return sum((parse(s["ended_at"]) - max(parse(s["started_at"]), start)).total_seconds() + SAMPLE_SECONDS
               for s in sessions if parse(s["ended_at"]) >= start) / 60


def drift(sessions, at, terms=(), strict=False):
    """Return (label, minutes) when the user is currently on a distraction and has been for a while."""
    start = at - timedelta(minutes=DRIFT_WINDOW_MINUTES)
    recent = [s for s in sessions if parse(s["ended_at"]) >= start]
    if not recent:
        return None
    latest = max(recent, key=lambda s: s["ended_at"])
    if (at - parse(latest["ended_at"])).total_seconds() > MERGE_GAP_SECONDS:
        return None
    if not is_distraction(latest["app"], latest["title"], terms, strict):
        return None
    total = 0.0
    for session in recent:
        if is_distraction(session["app"], session["title"], terms, strict):
            begin = max(parse(session["started_at"]), start)
            total += (parse(session["ended_at"]) - begin).total_seconds() + SAMPLE_SECONDS
    if total < DRIFT_THRESHOLD_MINUTES * 60:
        return None
    return label(latest), round(total / 60)


def utcnow():
    return datetime.now(timezone.utc)
