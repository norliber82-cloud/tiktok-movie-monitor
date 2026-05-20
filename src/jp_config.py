"""Japan-region monitor configuration.

This config OVERRIDES selected values from src.config for the JP-only
workflow. Everything else (classifier rules, tier definitions, etc.)
is reused from src.config to keep them in sync.
"""

# =========================================================
# Japan hashtag pool — bigger and more focused than the
# JP slice in the global pool, since this is JP-dedicated.
# =========================================================
JP_HASHTAGS = [
    # Core movie commentary
    "映画紹介", "映画考察", "映画解説", "映画レビュー", "映画の感想",
    "映画感想", "映画感想垢", "映画の話", "映画好き同士で繋がろう",
    # Lists & recs
    "おすすめ映画", "おすすめ映画教えて", "映画好きな人と繋がりたい",
    "映画好き", "映画好きと繋がりたい", "映画好き集まれ",
    "週末映画", "今日の映画",
    # Community
    "映画部", "映画オタク", "映画館", "映画ニュース", "映画クラスタ",
    # Genre tags (highly active)
    "ホラー映画", "ホラー映画好き", "ホラー映画好きな人と繋がりたい",
    "アクション映画", "恋愛映画", "コメディ映画", "アニメ映画",
    "邦画", "邦画レビュー", "邦画好き", "洋画", "洋画好き",
    # Streaming-specific (very high volume)
    "Netflix映画", "ネトフリ", "ネトフリ映画",
    "アマプラ", "Amazonプライム", "アマプラ映画",
    "Disney+", "ディズニープラス",
]

# Discovery-only pool (for seeding mid-tier creator candidates)
JP_DISCOVERY_HASHTAGS = [
    "映画紹介bot", "映画大好き", "映画感想ノート",
    "映画好きと繋がりたい", "映画ブログ",
    "邦画好きな人と繋がりたい", "洋画好きな人と繋がりたい",
    "ホラー好きな人と繋がりたい", "ネトフリで観れる",
    "ベスト映画", "名作映画",
]

# =========================================================
# Language filter — only Japanese
# =========================================================
JP_ALLOWED_LANGUAGES = {"ja"}

# =========================================================
# Tier thresholds (slightly lower than US since JP TikTok has
# smaller absolute view counts; you can tune later)
# =========================================================
JP_TIERS = [
    ("RED",    "🔥🇯🇵 500K+ · 3d",    "red",    500_000, 72, 1),
    ("ORANGE", "🟧🇯🇵 200K+ · 48h",   "orange", 200_000, 48, 2),
    ("YELLOW", "🟡🇯🇵 50K+ · 24h",    "yellow",  50_000, 24, 3),
]

# =========================================================
# Scraping behaviour
# =========================================================
JP_PER_TAG_LIMIT           = 200
JP_PER_DISCOVERY_TAG_LIMIT = 80
JP_SLEEP_BETWEEN_TAGS      = 4
JP_SLEEP_BETWEEN_CREATORS  = 5

# =========================================================
# Creator monitor — slightly relaxed for the smaller JP pool
# =========================================================
JP_CREATOR_MEDIAN_MIN          = 5_000     # 比海外低
JP_CREATOR_MEDIAN_MAX          = 100_000
JP_CREATOR_VIRAL_MULTIPLIER    = 5
JP_CREATOR_VIRAL_MIN           = 200_000
JP_CREATORS_EVAL_BUDGET        = 100

# =========================================================
# Duration filter
# =========================================================
JP_MIN_DURATION_SECONDS = 20
JP_MAX_DURATION_SECONDS = 600
