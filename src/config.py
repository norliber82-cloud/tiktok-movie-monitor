"""Central configuration for the monitor."""

# =========================================================
# Hashtag pools (no '#' prefix)
# =========================================================

HASHTAGS_EN = [
    "movietok", "filmtok", "endingexplained", "moviebreakdown",
    "hiddenmoviedetails", "movierecap", "moviecommentary",
    "scenebreakdown", "filmexplained", "movieanalysis",
]

HASHTAGS_JA = [
    "映画紹介", "映画考察", "映画解説", "映画レビュー",
    "おすすめ映画", "映画の感想",
]

HASHTAGS_ZH = [
    "电影解说", "影视解说",
]

# Primary scan pool — drives tier RED/ORANGE/YELLOW video alerts.
HASHTAGS = HASHTAGS_EN + HASHTAGS_JA

# Mid-volume pool used mainly to seed the creator-discovery queue.
# These tags tend to host creators with 10k–100k median plays.
DISCOVERY_HASHTAGS = [
    "filmcritic", "cinephile", "movietiktok", "moviebuff",
    "filmessay", "cinematok",
    "映画オタク", "映画感想",
    "电影解说", "影视解说", "电影推荐",
]

# =========================================================
# Movie-commentary classifier keywords
# =========================================================

KEYWORDS_IN = [
    "ending explained", "movie recap", "full movie in",
    "film breakdown", "scene breakdown", "hidden detail",
    "this shot", "director's trick", "you missed",
    "what nobody noticed", "movie analysis", "film analysis",
    "movie commentary",
    "映画紹介", "映画考察", "映画解説", "ネタバレ",
    "电影解说", "影视解说", "剧情解说",
]

KEYWORDS_OUT = [
    "fan edit", "fancam", "fan cam", "compilation of",
    "tiktok dance", "cosplay", " edit ", "edit)", "edit.",
    "thirst trap",
]

# =========================================================
# Video tier definitions  (strict → lenient)
#   (code, label, header_color, min_views, max_age_hours, rank)
# Lower rank number = more important.
# =========================================================
TIERS = [
    ("RED",    "🔥 1M+ · within 3d",    "red",    1_000_000, 72, 1),
    ("ORANGE", "🟧 500K+ · within 24h", "orange",   500_000, 24, 2),
    ("YELLOW", "🟡 200K+ · within 12h", "yellow",   200_000, 12, 3),
]

# Outermost posting-age window (the biggest of all tier windows, in days)
WINDOW_DAYS = 3

# =========================================================
# Creator-monitor thresholds
# =========================================================
CREATOR_MEDIAN_MIN          = 10_000     # floor  (封死量下限)
CREATOR_MEDIAN_MAX          = 100_000    # ceiling (封死量上限)
CREATOR_VIRAL_MULTIPLIER    = 5
CREATOR_VIRAL_MIN           = 500_000
CREATOR_VIRAL_WINDOW_DAY    = 7
CREATOR_CADENCE_14D_MIN     = 5
CREATOR_CADENCE_30D_MIN     = 10
CREATOR_VERTICAL_RATIO_MIN  = 0.4
CREATOR_SAMPLE_SIZE         = 30

# API-budget limits
CREATORS_EVAL_BUDGET_PER_RUN    = 12
CREATOR_REJECT_REEVAL_DAYS      = 14
CREATOR_MONITORED_REFRESH_DAYS  = 3

# =========================================================
# Scraping behaviour
# =========================================================
PER_TAG_LIMIT           = 150
PER_DISCOVERY_TAG_LIMIT = 60
SLEEP_BETWEEN_TAGS      = 4
SLEEP_BETWEEN_CREATORS  = 5
SESSION_SLEEP_AFTER     = 3
HEADLESS                = True
BROWSER                 = "webkit"
