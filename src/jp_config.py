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
    ("RED",    "🔥🇯🇵 200K+ · 7d",    "red",    200_000, 168, 1),
    ("ORANGE", "🟧🇯🇵 80K+ · 7d",    "orange",  80_000, 168, 2),
    ("YELLOW", "🟡🇯🇵 25K+ · 5d",    "yellow",  25_000, 120, 3),
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
# Duration filter — JP commentary videos are typically 30s-5min.
# Bumping the minimum from 20 to 30 cuts out memes / clips while
# keeping legitimate short recaps.
# =========================================================
JP_MIN_DURATION_SECONDS = 30
JP_MAX_DURATION_SECONDS = 600


# =========================================================
# JP-specific filters — designed for VOICEOVER COMMENTARY ONLY
#
# Goal: only collect videos where:
#   - Visual: clips of movie/TV footage being shown
#   - Audio: narrator voiceover explaining the plot/scenes
#   - NOT: creator on-camera reviewing or discussing
#
# This is hard to tell from caption alone — these signals are
# heuristics, not perfect. Combined with whitelist + AI vision
# (separate Gemini workflow) for full coverage.
# =========================================================

# === Voiceover-narration signals (third-person plot description) ===
# These are the kind of phrases that almost always belong to a
# voiceover narrating a movie's events ("the protagonist did X,
# then Y happened"). Strong positive signal.
JP_NARRATIVE_SIGNALS = [
    # Third-person subject markers
    "少女が", "少女は", "少年が", "少年は",
    "主人公は", "主人公が", "彼は", "彼女は", "彼らは",
    "男は", "女は", "男が", "女が",
    "親子は", "夫婦は", "兄弟は",
    # Plot-progression connectors (narrator sentences)
    "ある日", "そして", "しかし", "実は",
    "なんと", "驚くべき", "突然", "次の瞬間",
    "目覚めると", "気づくと", "やがて",
    "最後には", "最終的に", "結末では",
    # Plot-action verbs in narration tense
    "解読", "発見", "巻き込まれ", "目撃",
    "襲われる", "追い詰められ", "逃げ出す",
    # Narrative time markers
    "数年後", "数日後", "翌日", "それから",
]

# === On-camera / personal-opinion signals (the creator IS the speaker) ===
# These signal the creator is on-camera or talking AS themselves
# (review / opinion / list video). We DOWNGRADE these.
JP_ON_CAMERA_SIGNALS = [
    # First-person pronouns
    "私は", "僕は", "俺は", "私が",
    # Personal opinion phrases
    "個人的に", "個人的な", "私的に",
    "好きなシーン", "お気に入り", "オススメは",
    "ベスト", "ランキング",
    # Q&A / list format (typically on-camera)
    "実写化するなら", "選ぶなら",
    "皆さんは", "あなたは", "教えてください",
    # Direct address (on-camera reviewer)
    "今回は", "今日は紹介",
    "見てみて", "見てください",
    "コメントで",
    # Critic/review style
    "レビュー回", "オススメ動画",
]

# === Strong commentary keywords (kept from before, refined) ===
# These almost guarantee voiceover commentary IF NOT combined with
# on-camera signals.
JP_STRONG_SIGNAL_KEYWORDS = [
    "解説", "解説動画", "ネタバレ",
    "あらすじ", "ストーリー解説", "物語の",
    "ラストシーン", "結末解説",
    "監督", "脚本", "主演",
    "新作映画", "公開予定",
    # NOTE: "考察" / "見どころ" REMOVED — these often appear in
    # on-camera analysis videos too.
]

# === Hard exclusions (no commentary value at all) ===
JP_KEYWORDS_OUT = [
    # Stage / theater / musical
    "劇団四季", "舞台レビュー", "ミュージカル",
    "舞台で", "演劇", "宝塚",
    # Short film / original content (not commentary)
    "ショートフィルム", "ショートドラマ", "kowazo",
    "オリジナル映画", "自主制作", "自作映画",
    # Meme / parody / comedy clip
    "平常運転", "吉本", "コント", "ものまね",
    # Behind-the-scenes / making-of (not commentary)
    "撮影現場", "メイキング", "セット見学",
    # Personal journal / vlog (not film analysis)
    "今日の出来事", "私の日常",
    # Live concert / event
    "ライブ", "コンサート", "舞台挨拶",
    # Trailer-only repost
    "予告編", "予告解禁", "新CM",
    # Manga / book review (not film)
    "漫画レビュー", "原作小説",
    # Cosplay / fan goods
    "コスプレ", "グッズ紹介",
    # Real-person fan discussion (idol / actor focus, not film)
    "推し活", "ファン交流", "握手会",
]


# =========================================================
# Verified voiceover commentary author whitelist
# Built from your JP liked videos + JP videos table (creators
# with 2+ tier-hits over time). These are heuristic high-confidence
# but NOT 100% — used as a positive signal, not auto-accept.
# =========================================================
JP_AUTHOR_WHITELIST = [
    "ailene.sylvia",
    "celeste.leah1",
    "cochran.drew",
    "csrb016",
    "drz2e6",
    "geleraparwejgill",
    "has0dcmrh3",
    "iaaywsgyevg",
    "jovay56",
    "jptenny",
    "kingfilm73",
    "kotonoha76",
    "maruta_eiga",
    "pearson.clara",
    "qtswi24313",            # added: confirmed voiceover style
    "returnpijk9",
    "rising.cut",
    "rosiemovie3",
    "rxlhwlwi1ff",
    "shohei_movie",
    "user14288137314685",
    "user1468540117676",
    "user1701384797009",
    "user2184467748220",
    "user3622256530160",     # added: confirmed voiceover (少女体験)
    "user48872371381513",
    "user49167986716517",
    "user5117521598335",
    "user516774066904",
    "user5220214481525",
    "user6502581233131",
    "vjklrluao03167",
    "good_story_97",         # added: confirmed voiceover style
]


# =========================================================
# Scoring function — combines all the heuristics above to
# decide whether a JP video is voiceover commentary.
# Returns ("KEEP" | "DROP", confidence, reason)
# =========================================================
def jp_classify_voiceover(caption: str, hashtags: list,
                          author_unique: str = "",
                          duration: int = 0) -> tuple[str, str, str]:
    """Determines if a JP video is voiceover-style movie commentary.

    Returns:
      verdict   : "KEEP" / "DROP"
      confidence: "高" / "中" / "低"
      reason    : human-readable string
    """
    cap_lower = (caption or "").lower()
    author = (author_unique or "").strip().lstrip("@")

    # Hard exclusions first
    for bad in JP_KEYWORDS_OUT:
        if bad.lower() in cap_lower:
            return ("DROP", "低", f"hard_exclude:{bad}")

    # Score signals
    narrative_hits = sum(1 for sig in JP_NARRATIVE_SIGNALS
                         if sig in caption)
    on_camera_hits = sum(1 for sig in JP_ON_CAMERA_SIGNALS
                         if sig in caption)
    strong_hits = sum(1 for kw in JP_STRONG_SIGNAL_KEYWORDS
                      if kw in caption)
    in_whitelist = author.lower() in {a.lower() for a in JP_AUTHOR_WHITELIST}

    # Decision tree
    # 1. Heavy on-camera signal → DROP
    if on_camera_hits >= 2 and narrative_hits == 0:
        return ("DROP", "低",
                f"on_camera={on_camera_hits} narrative=0")

    # 2. Whitelist + any positive signal → KEEP high
    if in_whitelist and (narrative_hits >= 1 or strong_hits >= 1):
        return ("KEEP", "高",
                f"whitelist+narr={narrative_hits} strong={strong_hits}")

    # 3. Whitelist alone → KEEP medium (might be borderline)
    if in_whitelist:
        return ("KEEP", "中", "whitelist_only")

    # 4. Strong narrative signal (3+ hits) → KEEP high
    if narrative_hits >= 3:
        return ("KEEP", "高",
                f"strong_narrative={narrative_hits}")

    # 5. Mix of narrative + strong keywords → KEEP medium
    if narrative_hits >= 1 and strong_hits >= 1:
        return ("KEEP", "中",
                f"narr={narrative_hits} strong={strong_hits}")

    # 6. Strong keywords only, no narrative + no on-camera → KEEP low
    # (could be either, give benefit of doubt for now)
    if strong_hits >= 2 and on_camera_hits == 0:
        return ("KEEP", "低",
                f"strong_kw={strong_hits} but no narrative")

    # 7. Default: drop ambiguous
    return ("DROP", "低",
            f"ambiguous narr={narrative_hits} oncam={on_camera_hits} strong={strong_hits}")
