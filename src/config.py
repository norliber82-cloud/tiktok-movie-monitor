"""Central configuration for the monitor."""

# Hashtag pool (no '#' prefix). Focused on movie commentary / recap / analysis.
HASHTAGS = [
    "movietok",
    "filmtok",
    "endingexplained",
    "moviebreakdown",
    "hiddenmoviedetails",
    "movierecap",
    "moviecommentary",
    "scenebreakdown",
    "filmexplained",
    "movieanalysis",
]

# Caption keywords that confirm movie commentary
KEYWORDS_IN = [
    "ending explained",
    "movie recap",
    "full movie in",
    "film breakdown",
    "scene breakdown",
    "hidden detail",
    "this shot",
    "director's trick",
    "you missed",
    "what nobody noticed",
    "movie analysis",
    "film analysis",
    "movie commentary",
]

# Caption keywords that exclude (fan edits, dances, cosplay, etc.)
KEYWORDS_OUT = [
    "fan edit",
    "fancam",
    "fan cam",
    "compilation of",
    "tiktok dance",
    "cosplay",
    " edit ",
    "edit)",
    "edit.",
    "thirst trap",
]

# Thresholds
MIN_VIEWS = 1_000_000       # >= 1M plays
WINDOW_DAYS = 3             # posted within last 3 days
PER_TAG_LIMIT = 150         # videos to fetch per hashtag per run

# Scraping behaviour
SLEEP_BETWEEN_TAGS = 6      # seconds
SESSION_SLEEP_AFTER = 3
HEADLESS = True
