"""Shared helpers for the Punk Records FC FPL agent.

Stdlib only, so the fetch/project layer runs without a venv. Only optimise.py
needs a third-party package (pulp).
"""

from __future__ import annotations

import base64
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE = ROOT / "state"
LOG = STATE / "log"
SUMMARIES = DATA / "element-summary"

BASE_URL = "https://fantasy.premierleague.com/api"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 punk-records-fc/1.0"

# --- game constants, mirrored from bootstrap-static game_config -------------
# validate.py --rules asserts these against the live API, so a mid-season rule
# change surfaces as a failure instead of silently skewing every projection.

POS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
SQUAD_QUOTA = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_MIN = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}
BUDGET = 1000  # tenths of a million
TEAM_LIMIT = 3
SQUAD_SIZE = 15
XI_SIZE = 11
MAX_FREE_TRANSFERS = 5

GOAL_PTS = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}
CS_PTS = {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0}
ASSIST_PTS = 3
CONCEDE_POS = {"GKP", "DEF"}  # -1 per 2 goals shipped

# Defensive contribution: +2, at most once per match, at these action counts.
# DEF counts clearances+blocks+interceptions+tackles; MID/FWD add recoveries.
DC_PTS = 2
DC_THRESHOLD = {"DEF": 10, "MID": 12, "FWD": 12}  # GKP not eligible

# Defensive-action counts are overdispersed, so Poisson misses in both
# directions. DC_SHAPE is the negative-binomial shape: smaller means fatter
# tails, and 0 falls back to Poisson x DC_DISPERSION. Both are set by
# scripts/backtest.py --tune against end-to-end accuracy, NOT by fitting the
# component in isolation -- log-loss on the component alone is maximised by a
# near-constant predictor that ranks players uselessly.
DC_DISPERSION = 0.90
DC_SHAPE = 0.0

LEAGUE_AVG_GOALS = 1.42  # goals per team per match
HOME_ADV = 1.10

# Weight on the structural model versus the player's observed points per
# appearance. The bottom-up model knows about fixtures, minutes and DefCon that
# raw scoring rate cannot see, but it is noisier. Measured over 2025/26 GW6-38:
# model alone rho 0.229, points-per-game alone 0.324, an even blend 0.355.
# Set by scripts/backtest.py --blend; do not change it without rerunning that.
FORM_BLEND = 0.5

# Discount applied to players projected from asserted minutes rather than
# observed history. Two reasons, both measured:
#   1. Replacement rates are the median over players with 900+ minutes -- a
#      survivor sample, so "replacement level" is really "median established
#      starter". An unproven player belongs below that.
#   2. Across the 2024/25 and 2025/26 promoted cohorts, midfield and forward
#      returns sat at 0.68-1.06 of established (mean ~0.85) even after team
#      quality is accounted for. Defender returns tracked goals conceded and
#      are handled by the team factor instead.
# These projections are the weakest numbers the model produces. Treat them as
# upper bounds, and revisit once real minutes exist after GW3-4.
ASSUMED_DISCOUNT = 0.85

# How strongly a 1-5 team rating bends expected goals. Calibration target.
STRENGTH_K = 0.35
# A starter is odds-on to reach 60 minutes; sub appearances add a little on top.
APPEAR_UPLIFT = 1.25


# --- env --------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Parse .env into a dict. A missing file is fine; callers handle absent keys."""
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("'\"")
    return env


# --- http -------------------------------------------------------------------

class FetchError(RuntimeError):
    """Carries an actionable message rather than a bare HTTPError."""


_SECRET_PARAMS = ("apiKey", "api_key", "apikey", "token", "key")


def redact(url: str) -> str:
    """Strip credentials out of a URL before it reaches a log or an error.

    Error messages quote the failing URL, and odds providers take the API key as
    a query parameter -- so without this a single timeout prints the key.
    """
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    parts = []
    for pair in query.split("&"):
        name, sep, _ = pair.partition("=")
        parts.append(f"{name}=***" if sep and name in _SECRET_PARAMS else pair)
    return f"{base}?{'&'.join(parts)}"


def token_expiry(token: str) -> float | None:
    """Read `exp` out of a JWT without verifying it.

    Local-only, and never used to trust the token -- only to turn an opaque 403
    into "your token expired at 18:33, grab a fresh one". FPL access tokens last
    about 8 hours, so expiry is the failure you will hit most.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


def http_get(url: str, retries: int = 3, bearer: str | None = None) -> dict:
    """GET JSON, with retries. `bearer` authenticates FPL's my-team endpoint.

    There is deliberately no cookie support: FPL's authenticated endpoints
    return 403 for every combination of the browser cookie jar, and 200 for
    `Authorization: Bearer <access_token>`. Accepting cookies would only offer
    a route that cannot work.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise FetchError(
                    f"{redact(url)} returned {exc.code}. Credentials are missing, "
                    "wrong or expired -- refresh them in .env (see README)."
                ) from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"{redact(url)} failed after {retries} attempts: {last}")


# --- cache ------------------------------------------------------------------

def cache_path(name: str) -> Path:
    return DATA / f"{name}.json"


def read_cache(path: Path, max_age_h: float | None = None):
    """Return cached JSON, or None when absent, stale or corrupt."""
    if not path.exists():
        return None
    if max_age_h is not None:
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if age_h > max_age_h:
            return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def write_cache(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1))


def load_bootstrap() -> dict:
    data = read_cache(cache_path("bootstrap-static"))
    if data is None:
        raise FetchError("No bootstrap cache. Run: python scripts/fetch.py --core")
    return data


def load_fixtures() -> list:
    data = read_cache(cache_path("fixtures"))
    if data is None:
        raise FetchError("No fixtures cache. Run: python scripts/fetch.py --core")
    return data


def load_summary(player_id: int):
    return read_cache(SUMMARIES / f"{player_id}.json")


# --- stats ------------------------------------------------------------------

def poisson_at_least(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 0.0
    if k <= 0:
        return 1.0
    cum = term = math.exp(-lam)  # P(X = 0)
    for i in range(1, k):
        term *= lam / i
        cum += term
    return max(0.0, min(1.0, 1.0 - cum))


def nbinom_at_least(k: int, mean: float, shape: float) -> float:
    """P(X >= k) for a negative binomial with the given mean and shape.

    Defensive-action counts are overdispersed: their variance exceeds their
    mean, because a player's involvement varies by game state, opponent and
    role. Poisson forces variance == mean, which then under-predicts the low
    band and over-predicts the high band -- both observed in the 2025/26
    backtest. The negative binomial has variance mean + mean^2/shape, so a
    smaller `shape` means fatter tails; shape -> infinity recovers Poisson.
    """
    if mean <= 0:
        return 0.0
    if k <= 0:
        return 1.0
    if shape <= 0:
        return poisson_at_least(k, mean)

    # p is the per-trial success probability in the standard parameterisation.
    p = shape / (shape + mean)
    # P(X = 0) = p**shape, then the usual recurrence for successive terms.
    term = p**shape
    cum = term
    for i in range(1, k):
        term *= (shape + i - 1) / i * (1 - p)
        cum += term
    return max(0.0, min(1.0, 1.0 - cum))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


def per90(total, minutes) -> float:
    return safe_div(float(total or 0) * 90.0, float(minutes or 0), 0.0)


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# --- scoring model ----------------------------------------------------------
# This is the single definition of expected points for one player in one
# fixture. project.py and backtest.py both call it, so the backtest measures
# the model that actually ships rather than a reimplementation of it.

def expected_concede_penalty(xg_against: float) -> float:
    """E[-floor(goals_conceded / 2)] under Poisson. The tail past 8 is nil."""
    penalty = 0.0
    for goals in range(1, 9):
        prob = math.exp(-xg_against) * xg_against**goals / math.factorial(goals)
        penalty -= prob * (goals // 2)
    return penalty


def fixture_points(
    pos: str,
    rates: dict,
    xmins: float,
    p_start: float,
    p_appear: float,
    xg_for: float,
    xg_against: float,
    fixture_mult: float,
    dc_dispersion: float = DC_DISPERSION,
    dc_shape: float = DC_SHAPE,
    form_blend: float = FORM_BLEND,
    avail: float = 1.0,
    components: bool = False,
) -> float | dict[str, float]:
    """Expected FPL points for one player in one fixture.

    `rates` holds per-90 rates: xg90, xa90, dc90, sv90, bonus90, yellow90.
    `fixture_mult` scales attacking output for fixture quality, relative to the
    player's own team baseline -- see projection-model.md on double counting.
    """
    mins_share = xmins / 90.0
    parts = {
        "appearance": 2 * p_start + 1 * max(0.0, p_appear - p_start),
        "goals": rates.get("xg90", 0.0) * mins_share * fixture_mult * GOAL_PTS[pos],
        "assists": rates.get("xa90", 0.0) * mins_share * fixture_mult * ASSIST_PTS,
        "clean_sheet": 0.0,
        "concede_penalty": 0.0,
        "saves": 0.0,
        "defcon": 0.0,
        "bonus": rates.get("bonus90", 0.0) * mins_share,
        "cards": -rates.get("yellow90", 0.0) * mins_share,
    }

    if CS_PTS[pos]:
        # A clean sheet needs 60 minutes, hence p_start rather than p_appear.
        parts["clean_sheet"] = math.exp(-xg_against) * CS_PTS[pos] * p_start
    if pos in CONCEDE_POS:
        parts["concede_penalty"] = expected_concede_penalty(xg_against) * p_start
    if pos == "GKP":
        parts["saves"] = rates.get("sv90", 0.0) * mins_share * (xg_against / LEAGUE_AVG_GOALS) / 3.0
    if pos in DC_THRESHOLD:
        lam = rates.get("dc90", 0.0) * mins_share
        if dc_shape > 0:
            p_hit = nbinom_at_least(DC_THRESHOLD[pos], lam, dc_shape)
        else:
            p_hit = poisson_at_least(DC_THRESHOLD[pos], lam) * dc_dispersion
        parts["defcon"] = p_hit * DC_PTS

    structural = sum(parts.values())
    pts = structural

    # Shrink toward what this player actually scores per appearance. The
    # structural model above reconstructs points from components and drifts;
    # the observed rate is blunt but unbiased. Blending beats either alone.
    # Scale the observed rate by availability -- a hard API signal (injured,
    # suspended, doubtful) -- rather than by the estimated appearance
    # probability. p_appear is derived from historical starts and is noisy
    # enough that multiplying by it measurably degrades ranking.
    ppg = rates.get("ppg")
    observed = 0.0
    structural_weight = 1.0
    if ppg is not None and form_blend > 0:
        structural_weight = 1 - form_blend
        observed = form_blend * ppg * avail
        pts = structural_weight * pts + observed
    if not components:
        return pts

    weighted = {key: value * structural_weight for key, value in parts.items()}
    weighted["observed"] = observed
    weighted["structural"] = structural
    weighted["total"] = pts
    return weighted


def fmt_price(tenths) -> str:
    return f"{float(tenths) / 10:.1f}"


def next_event(bootstrap: dict):
    for event in bootstrap["events"]:
        if event.get("is_next"):
            return event
    for event in bootstrap["events"]:
        if not event.get("finished"):
            return event
    return None


# --- deadlines --------------------------------------------------------------
# The manager is in Sydney; FPL publishes deadlines in UTC. Across 2026/27 that
# puts 17 deadlines just past midnight Sunday local, 5 at ~05:30 Thursday and 4
# at ~03:30 Saturday, so "act two hours before the deadline" is unusable here.
# Every user-facing time is therefore rendered in Sydney local, and the lock
# session is pinned to the last civil evening before the deadline instead.
#
# ZoneInfo handles the AEST/AEDT switch (AEDT from 4 Oct 2026 to 4 Apr 2027),
# so never hardcode a UTC offset.

# Defaults to Sydney because that is where this was built, and the overnight
# deadlines it works around are a Sydney problem. Anyone elsewhere should set
# FPL_TIMEZONE in .env to their own IANA zone -- an unset zone would otherwise
# report confidently wrong lock times, which is worse than reporting none.
def _local_zone() -> ZoneInfo:
    import os
    name = (os.environ.get("FPL_TIMEZONE") or load_env().get("FPL_TIMEZONE", "")).strip()
    if not name:
        return ZoneInfo("Australia/Sydney")
    try:
        return ZoneInfo(name)
    except Exception:
        print(f"warning: FPL_TIMEZONE={name!r} is not a valid IANA zone; "
              "falling back to Australia/Sydney", file=__import__("sys").stderr)
        return ZoneInfo("Australia/Sydney")


SYDNEY = _local_zone()  # kept as the name callers already use
LOCAL_ZONE_LABEL = str(SYDNEY)  # e.g. "Australia/Sydney" -- for user-facing labels
CIVIL_START_H = 7    # earliest hour we would ask a human to act
CIVIL_EVENING_H = 21  # fallback slot when the deadline lands overnight
LOCK_LEAD = timedelta(minutes=90)
PLAN_LEAD_DAYS = 3


def parse_utc(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def to_sydney(moment: datetime) -> datetime:
    return moment.astimezone(SYDNEY)


def fmt_syd(moment: datetime) -> str:
    """e.g. 'Sat 22 Aug 03:30 AEST'."""
    local = to_sydney(moment)
    return f"{local:%a %d %b %H:%M} {local.tzname()}"


def lock_session(deadline_utc: datetime) -> datetime:
    """Latest sensible Sydney-local moment to finalise before a deadline.

    Normally 90 minutes out. When that lands between midnight and 07:00 local,
    it falls back to 21:00 the previous evening -- still after the UK Friday
    press conferences, since Sydney evening is UK midday.
    """
    latest = to_sydney(deadline_utc - LOCK_LEAD)
    if latest.hour >= CIVIL_START_H:
        return latest
    return (latest - timedelta(days=1)).replace(
        hour=CIVIL_EVENING_H, minute=0, second=0, microsecond=0
    )


def plan_session(deadline_utc: datetime) -> datetime:
    """Sydney-local slot for the early planning pass, a few days ahead."""
    lock = lock_session(deadline_utc)
    return (lock - timedelta(days=PLAN_LEAD_DAYS)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )


def deadline_brief(event: dict) -> dict:
    """Everything a human needs about when to act on one gameweek."""
    deadline = parse_utc(event["deadline_time"])
    lock = lock_session(deadline)
    now = datetime.now(timezone.utc)
    return {
        "gw": event["id"],
        "deadline_utc": deadline,
        "deadline_syd": fmt_syd(deadline),
        "plan_syd": fmt_syd(plan_session(deadline)),
        "lock_syd": fmt_syd(lock),
        "overnight": to_sydney(deadline).hour < CIVIL_START_H,
        "hours_to_deadline": (deadline - now).total_seconds() / 3600,
        "hours_to_lock": (lock - now).total_seconds() / 3600,
    }
