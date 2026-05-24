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
    # ========== Tier S: 实测最有效（你点赞数据显示的高频标签） ==========
    "映画", "映画紹介", "映画解説", "映画鑑賞",
    "映画ホリック", "映画レビュー",

    # ========== Tier A: Core movie commentary ==========
    "映画考察", "映画の感想", "映画感想", "映画感想垢",
    "映画の話", "映画好き同士で繋がろう",

    # ========== Tier A: 中文风格但日语圈在用 ==========
    "映画介绍", "映画介紹", "映画绍介",  # 海外日本人用得多

    # ========== Tier A: 日语+英语混合（爆款常用） ==========
    "movietok", "moviereview", "filmbreaker", "japanesemovie",
    "日本映画", "外道の歌",

    # ========== Tier B: Lists & recs ==========
    "おすすめ映画", "おすすめ映画教えて", "映画好きな人と繋がりたい",
    "映画好き", "映画好きと繋がりたい", "映画好き集まれ",
    "週末映画", "今日の映画", "ベスト映画", "名作映画",

    # ========== Tier B: Community ==========
    "映画部", "映画オタク", "映画館", "映画ニュース", "映画クラスタ",

    # ========== Tier B: Genre tags ==========
    "ホラー映画", "ホラー映画好き", "ホラー映画好きな人と繋がりたい",
    "アクション映画", "恋愛映画", "コメディ映画", "アニメ映画",
    "邦画", "邦画レビュー", "邦画好き", "洋画", "洋画好き",
    "怪獣", "SF映画", "ミステリー映画", "サスペンス映画",

    # ========== Tier B: Streaming ==========
    "Netflix映画", "ネトフリ", "ネトフリ映画",
    "アマプラ", "Amazonプライム", "アマプラ映画",
    "Disney+", "ディズニープラス", "ネトフリで観れる",

    # ========== Tier B: Contest / promotional ==========
    "TikTok映画TVコンテスト", "TikTokFilmTVCompetition",
    "tiktoktvfilmcontest", "ハイスコアの映画推薦",
    "映画とテレビの解説は人気があります", "映画とテレビの推薦",

    # ======== EXPANSION: 解説類（Commentary/Deep Analysis）========
    "映画まとめ", "映画語り", "映画オススメ", "映画ノート",
    "映画備忘録", "映画日記", "映画ログ", "映画時々",
    "映画を語る", "映画を見た", "今日の映画記録",

    # ======== EXPANSION: ホラー/サスペンス（Horror/Suspense）========
    "ホラー好き", "ホラー映画おすすめ", "心霊",
    "絶叫注意", "怖い話", "怪談", "考察系ホラー",

    # ======== EXPANSION: 暗黒/心理（Dark/Psychological）========
    "胸糞映画", "鬱映画", "泣ける映画", "感動映画",
    "後味悪い映画", "胸糞注意", "トラウマ映画",

    # ======== EXPANSION: 日本チャンネル/番組（JP Channels/Series）========
    "ドラマ", "日本ドラマ", "韓国ドラマ",
    "海外ドラマ", "アニメ", "アニメ考察", "漫画",
    "WOWOW", "U-NEXT", "hulu",

    # ======== EXPANSION: 高再生/バズ狙い（High-Play / Viral Targeting）========
    "バズれ", "おすすめにのりたい", "見つけたら",
    "話題の映画", "ちょっと待って", "最後まで見て",
    "知らないと損する", "ヤバい映画",

    # ======== EXPANSION: コミュニティ/交差（Community / Crossover）========
    "映画好きさんと繋がりたい", "映画垢", "映画垢さんと繋がりたい",
    "映画スタグラム", "TikTok映画部", "映画あるある",
    "映画の名言", "映画音楽", "映画の世界観",
]

# Discovery-only pool (for seeding mid-tier creator candidates)
JP_DISCOVERY_HASHTAGS = [
    "映画紹介bot", "映画大好き", "映画感想ノート",
    "映画好きと繋がりたい", "映画ブログ",
    "邦画好きな人と繋がりたい", "洋画好きな人と繋がりたい",
    "ホラー好きな人と繋がりたい", "ネトフリで観れる",
    "ベスト映画", "名作映画",
    # EXPANSION: mid-tier discovery boosters
    "映画垢", "映画垢さんと繋がりたい", "映画好きさんと繋がりたい",
    "映画オススメ", "映画備忘録", "映画ノート",
]

# =========================================================
# Language filter — only Japanese
# =========================================================
JP_ALLOWED_LANGUAGES = {"ja"}

# =========================================================
# Tier thresholds — calibrated against actual JP liked-video
# data (median 320K plays, P25 100K, P75 1.3M). Old thresholds
# were 500K/200K/50K, but real engagement is lower than US so
# we relax further to surface more candidates.
# =========================================================
JP_TIERS = [
    ("RED",    "🔥🇯🇵 300K+ · 7d",    "red",    300_000, 168, 1),
    ("ORANGE", "🟧🇯🇵 100K+ · 5d",   "orange", 100_000, 120, 2),
    ("YELLOW", "🟡🇯🇵 30K+ · 3d",    "yellow",  30_000,  72, 3),
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
