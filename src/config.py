"""Central configuration for the monitor."""

# =========================================================
# TikTok hashtag pools (no '#' prefix)
# =========================================================

HASHTAGS_EN = [
    # Commentary / analysis
    "movietok", "filmtok", "endingexplained", "moviebreakdown",
    "hiddenmoviedetails", "movierecap", "moviecommentary",
    "scenebreakdown", "filmexplained", "movieanalysis",
    "filmcritique", "filmtheory", "moviemistakes",
    # Lists / recs
    "movierecommendations", "moviestowatch", "scarymovies",
    "topmovies", "cultmovies",
    # Genre-specific (deep recap goldmines)
    "horrormovies", "horrortok", "sciencefiction", "sciencefictionmovies",
    "thrillertok", "netflixmovies",
    # +20 expansion
    "actionmovies", "comedymovies", "romcom", "mysterymovies",
    "crimemovies", "a24films", "marvelstudios", "dcfilms",
    "netflixoriginal", "moviereaction", "moviefacts",
    "bestmoviescenes", "moviequotes", "filmnerd",
    "movieclips", "cinematography", "classicmovies", "indiefilm",
]

HASHTAGS_JA = [
    # Core commentary
    "映画紹介", "映画考察", "映画解説", "映画レビュー", "映画の感想",
    "映画感想", "映画感想垢",
    # Lists / recs
    "おすすめ映画", "おすすめ映画教えて", "映画好きな人と繋がりたい",
    "映画好き", "映画好きと繋がりたい",
    # Community
    "映画部", "映画オタク", "映画館", "映画ニュース",
    # Genre
    "ホラー映画", "ホラー映画好き", "邦画", "洋画", "恋愛映画",
    "アクション映画", "邦画レビュー",
    # Streaming-specific (very active in JP)
    "Netflix映画", "アマプラ", "Amazonプライム",
]

HASHTAGS_ZH = [
    "电影解说", "影视解说",
]

# Primary scan pool — drives tier RED/ORANGE/YELLOW video alerts.
HASHTAGS = HASHTAGS_EN + HASHTAGS_JA

# Mid-volume pool used mainly to seed the creator-discovery queue.
DISCOVERY_HASHTAGS = [
    "filmcritic", "cinephile", "movietiktok", "moviebuff",
    "filmessay", "cinematok", "movienerd", "cinephiletok",
    "filmbro", "criterion",
    "映画オタク", "映画感想", "映画好き",
    "电影解说", "影视解说", "电影推荐",
]

# =========================================================
# Movie-commentary classifier keywords
# =========================================================

KEYWORDS_IN = [
    # English
    "ending explained", "movie recap", "full movie in",
    "film breakdown", "scene breakdown", "hidden detail",
    "this shot", "director's trick", "you missed",
    "what nobody noticed", "movie analysis", "film analysis",
    "movie commentary", "plot explained", "film theory",
    "movie explained", "in this movie", "why this movie",
    # Japanese
    "映画紹介", "映画考察", "映画解説", "ネタバレ", "映画レビュー",
    # Chinese
    "电影解说", "影视解说", "剧情解说", "电影推荐",
]

KEYWORDS_OUT = [
    "fan edit", "fancam", "fan cam", "compilation of",
    "tiktok dance", "cosplay", " edit ", "edit)", "edit.",
    "thirst trap", "tribute",
]

# =========================================================
# Language filter
# =========================================================
# Only persist videos in these languages. Hits in other languages are
# completely dropped (not stored, not pushed, not synced).
ALLOWED_LANGUAGES = {"en", "ja"}
#   (code, label, header_color, min_views, max_age_hours, rank)
# =========================================================
TIERS = [
    ("RED",    "🔥 1M+ · within 3d",    "red",    1_000_000, 72, 1),
    ("ORANGE", "🟧 500K+ · within 48h", "orange",   500_000, 48, 2),
    ("YELLOW", "🟡 100K+ · within 24h", "yellow",   100_000, 24, 3),
]

WINDOW_DAYS = 3

# =========================================================
# Creator-monitor thresholds
# =========================================================
CREATOR_MEDIAN_MIN          = 10_000
CREATOR_MEDIAN_MAX          = 100_000
CREATOR_VIRAL_MULTIPLIER    = 5
CREATOR_VIRAL_MIN           = 500_000
CREATOR_VIRAL_WINDOW_DAY    = 7
CREATOR_CADENCE_14D_MIN     = 5
CREATOR_CADENCE_30D_MIN     = 10
CREATOR_VERTICAL_RATIO_MIN  = 0.4
CREATOR_SAMPLE_SIZE         = 30

CREATORS_EVAL_BUDGET_PER_RUN    = 100
CREATOR_REJECT_REEVAL_DAYS      = 14
CREATOR_MONITORED_REFRESH_DAYS  = 3

# =========================================================
# Duration filter (avoid raw clips <20s and full reposts >600s)
# =========================================================
MIN_DURATION_SECONDS = 20
MAX_DURATION_SECONDS = 600
PER_TAG_LIMIT           = 200
PER_DISCOVERY_TAG_LIMIT = 80
SLEEP_BETWEEN_TAGS      = 3
SLEEP_BETWEEN_CREATORS  = 5
SESSION_SLEEP_AFTER     = 3
HEADLESS                = True
BROWSER                 = "webkit"

# =========================================================
# YouTube Shorts monitoring
# =========================================================
YT_SEARCH_QUERIES = [
    "movie recap",
    "movie explained shorts",
    "ending explained shorts",
    "film analysis shorts",
    "hidden movie details",
    "映画 考察 shorts",
    "映画 解説 shorts",
]
YT_PER_QUERY_LIMIT = 40
YT_SHORTS_MAX_DURATION = 180  # seconds; anything longer is a full video
YT_MIN_TIER_VIEWS = 100_000   # YouTube Shorts tier floor (uses same TIERS above)
