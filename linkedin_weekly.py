#!/usr/bin/env python3
"""
LinkedIn Weekly Post Generator
Fetches trending game dev content and drafts LinkedIn posts using AI.
"""

import os
import re
import sys
import json

# Force UTF-8 output so emojis work on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import datetime
import subprocess
import time
import requests
import feedparser
from pathlib import Path
from dotenv import load_dotenv
import anthropic

# ── Load env vars ─────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).parent / "reports"

REDDIT_SUBREDDITS = [
    "gamedev",
    "indiegaming",
    "programming",
    "cscareerquestions",
]

GAMASUTRA_RSS_URL = "https://www.gamedeveloper.com/rss.xml"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
NUM_DRAFTS = 3
REDDIT_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT",
    "python:linkedin-weekly:1.0 (personal weekly digest script)",
)
HTTP_HEADERS = {
    "User-Agent": REDDIT_USER_AGENT,
    "Accept": "application/atom+xml,application/rss+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

HN_KEYWORDS = [
    "game", "gaming", "dev", "developer", "programming", "software",
    "engineer", "career", "layoff", "studio", "indie", "unity",
    "unreal", "engine", "graphics", "render", "shader", "job",
]


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()[:300]


def fetch_reddit_posts(subreddits: list[str], limit: int = 20) -> list[dict]:
    """Fetch top posts from the past week via Reddit RSS (JSON endpoints often 403)."""
    posts = []
    for sub in subreddits:
        rss_urls = [
            f"https://www.reddit.com/r/{sub}/top/.rss?t=week&limit={limit}",
            f"https://old.reddit.com/r/{sub}/top/.rss?t=week&limit={limit}",
        ]
        fetched = False
        for url in rss_urls:
            try:
                feed = feedparser.parse(url, request_headers=HTTP_HEADERS)
                if getattr(feed, "status", None) == 403 or not feed.entries:
                    continue
                entries = feed.entries[:limit]
                for i, entry in enumerate(entries):
                    rank = limit - i
                    snippet = ""
                    if entry.get("content"):
                        snippet = _strip_html(entry.content[0].get("value", ""))
                    elif entry.get("summary"):
                        snippet = _strip_html(entry.summary)
                    posts.append({
                        "source": f"r/{sub}",
                        "title": entry.get("title", ""),
                        "score": rank * 100,
                        "comments": 0,
                        "url": entry.get("link", ""),
                        "snippet": snippet,
                    })
                print(f"    ✓ r/{sub} — {len(entries)} posts (RSS)")
                fetched = True
                break
            except Exception:
                continue
        if not fetched:
            print(f"    ⚠  r/{sub} failed: Reddit RSS blocked or unavailable")
        time.sleep(0.5)
    return posts


def fetch_hackernews_posts(limit: int = 15) -> list[dict]:
    """Fetch top HN stories relevant to game dev / programming (Algolia API)."""
    posts = []
    try:
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"tags": "front_page", "hitsPerPage": 100},
            headers=HTTP_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            title = hit.get("title") or ""
            if not any(kw in title.lower() for kw in HN_KEYWORDS):
                continue
            story_id = hit.get("story_id") or hit.get("objectID")
            posts.append({
                "source": "Hacker News",
                "title": title,
                "score": hit.get("points") or 0,
                "comments": hit.get("num_comments") or 0,
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}",
                "snippet": "",
            })
        posts.sort(key=lambda p: p["score"], reverse=True)
        posts = posts[:limit]
        print(f"    ✓ Hacker News — {len(posts)} relevant stories")
    except Exception as exc:
        print(f"    ⚠  Hacker News failed: {exc}")
    return posts


def fetch_gamasutra_posts(limit: int = 10) -> list[dict]:
    """Fetch recent articles from Game Developer Magazine RSS."""
    posts = []
    try:
        feed = feedparser.parse(GAMASUTRA_RSS_URL)
        for entry in feed.entries[:limit]:
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:300].strip()
            posts.append({
                "source": "Game Developer Magazine",
                "title": entry.get("title", ""),
                "score": 150,
                "comments": 0,
                "url": entry.get("link", ""),
                "snippet": summary,
            })
        print(f"    ✓ Game Developer Magazine — {len(posts)} articles")
    except Exception as exc:
        print(f"    ⚠  Gamasutra RSS failed: {exc}")
    return posts


# ── Ranking ───────────────────────────────────────────────────────────────────

def rank_content(all_posts: list[dict], top_n: int = 15) -> list[dict]:
    """Rank posts by a weighted engagement score."""
    for p in all_posts:
        p["engagement"] = p["score"] + (p["comments"] * 3)
    ranked = sorted(all_posts, key=lambda x: x["engagement"], reverse=True)
    return ranked[:top_n]


# ── AI Drafting ───────────────────────────────────────────────────────────

def generate_drafts(top_content: list[dict], api_key: str) -> dict:
    """Use Claude to generate 3 LinkedIn post drafts."""
    client = anthropic.Anthropic(api_key=api_key)

    content_summary = "\n".join(
        f"- [{p['source']}] {p['title']} (score: {p['engagement']})"
        + (f"\n  Context: {p['snippet']}" if p["snippet"] else "")
        for p in top_content[:12]
    )

    prompt = f"""You are helping a video game developer and programmer from West Yorkshire, UK, 
write weekly LinkedIn posts to stay visible in their professional network — especially important 
during the current wave of games industry layoffs.

Here are the most engaging topics in the game dev and programming community this week:

{content_summary}

Based on these trending topics, write exactly {NUM_DRAFTS} distinct LinkedIn post drafts.

Each draft MUST:
- Be casual, fun, and light-hearted — genuine personality, a dry wit, maybe a touch of Northern humour
- Be short and punchy — strictly 3 to 5 sentences, no more
- Feel like a real human wrote it, not a PR department or a robot
- Be about game development, programming, or the career side of the industry
- End with a question or soft call-to-action to invite comments
- Have a different opening style to the others — vary hooks (question, bold statement, story, observation)
- Be ready to copy-paste and post with only light personal tweaks needed

Make the 3 drafts noticeably different in angle and format from each other.

Return your response as valid JSON only — no markdown, no extra text — using this exact structure:
{{
  "drafts": [
    {{
      "title": "Short descriptive label for this draft (e.g. 'The Hot Take')",
      "inspiration": "One sentence: which trending topic inspired this and why",
      "post": "The actual LinkedIn post text, ready to copy"
    }}
  ]
}}"""

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ── HTML Report ───────────────────────────────────────────────────────────────

def render_html_report(top_content: list[dict], drafts_data: dict, run_date: datetime.datetime) -> str:
    """Render a beautiful, self-contained HTML report."""

    date_str = run_date.strftime("%A, %d %B %Y")
    time_str = run_date.strftime("%H:%M")

    # Build trending topics HTML
    source_colours = {
        "r/gamedev": "#7c3aed",
        "r/indiegaming": "#9333ea",
        "r/programming": "#2563eb",
        "r/cscareerquestions": "#0891b2",
        "Hacker News": "#ea580c",
        "Game Developer Magazine": "#16a34a",
    }

    topics_html = ""
    for i, post in enumerate(top_content, 1):
        colour = source_colours.get(post["source"], "#6b7280")
        snippet_html = f'<p class="topic-snippet">{post["snippet"]}</p>' if post["snippet"] else ""
        topics_html += f"""
        <div class="topic-card">
            <div class="topic-rank">#{i}</div>
            <div class="topic-body">
                <span class="topic-badge" style="background:{colour}22;color:{colour};border:1px solid {colour}44">{post['source']}</span>
                <a class="topic-title" href="{post['url']}" target="_blank" rel="noopener">{post['title']}</a>
                {snippet_html}
                <div class="topic-stats">
                    <span>⬆ {post['score']:,}</span>
                    <span>💬 {post['comments']:,}</span>
                    <span>🔥 Engagement: {post['engagement']:,}</span>
                </div>
            </div>
        </div>"""

    # Build draft posts HTML
    draft_colours = ["#7c3aed", "#06b6d4", "#f59e0b"]
    draft_icons = ["✍️", "💡", "🚀"]
    drafts_html = ""
    for i, draft in enumerate(drafts_data.get("drafts", [])):
        colour = draft_colours[i % len(draft_colours)]
        icon = draft_icons[i % len(draft_icons)]
        post_text = draft["post"].replace("\n", "<br>")
        post_escaped = draft["post"].replace("`", "\\`").replace("\\", "\\\\")
        drafts_html += f"""
        <div class="draft-card" style="--accent:{colour}">
            <div class="draft-header">
                <div class="draft-icon">{icon}</div>
                <div>
                    <h3 class="draft-title">{draft['title']}</h3>
                    <p class="draft-inspiration">💭 {draft['inspiration']}</p>
                </div>
                <button class="copy-btn" onclick="copyDraft(this, `{post_escaped}`)" title="Copy to clipboard">
                    📋 Copy
                </button>
            </div>
            <div class="draft-post">{post_text}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkedIn Weekly — {date_str}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        :root {{
            --bg: #0b0b12;
            --surface: #13131f;
            --card: #1a1a2e;
            --border: rgba(255,255,255,0.07);
            --text: #e2e8f0;
            --muted: #94a3b8;
            --purple: #7c3aed;
            --cyan: #06b6d4;
            --amber: #f59e0b;
            --green: #10b981;
        }}

        body {{
            font-family: 'Inter', system-ui, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 0 0 80px;
        }}

        /* ── Header ── */
        .header {{
            background: linear-gradient(135deg, #0f0f1e 0%, #1a0a2e 50%, #0a1628 100%);
            border-bottom: 1px solid var(--border);
            padding: 48px 40px 40px;
            position: relative;
            overflow: hidden;
        }}
        .header::before {{
            content: '';
            position: absolute;
            top: -80px; right: -80px;
            width: 400px; height: 400px;
            background: radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 70%);
            pointer-events: none;
        }}
        .header::after {{
            content: '';
            position: absolute;
            bottom: -60px; left: 30%;
            width: 300px; height: 300px;
            background: radial-gradient(circle, rgba(6,182,212,0.08) 0%, transparent 70%);
            pointer-events: none;
        }}
        .header-inner {{
            max-width: 1100px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
        }}
        .header-eyebrow {{
            display: flex; align-items: center; gap: 10px;
            margin-bottom: 16px;
        }}
        .header-pill {{
            background: rgba(124,58,237,0.2);
            border: 1px solid rgba(124,58,237,0.4);
            color: #a78bfa;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            padding: 4px 12px;
            border-radius: 100px;
        }}
        .header-dot {{
            width: 6px; height: 6px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 8px var(--green);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.6; transform: scale(1.3); }}
        }}
        h1 {{
            font-size: clamp(28px, 4vw, 42px);
            font-weight: 700;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #fff 30%, #a78bfa 70%, #67e8f9 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 8px;
        }}
        .header-meta {{
            color: var(--muted);
            font-size: 14px;
        }}
        .header-stats {{
            display: flex; gap: 24px; margin-top: 28px; flex-wrap: wrap;
        }}
        .stat {{
            display: flex; align-items: center; gap: 8px;
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 16px;
        }}
        .stat-num {{ font-size: 20px; font-weight: 700; color: #fff; }}
        .stat-label {{ font-size: 12px; color: var(--muted); margin-top: 1px; }}

        /* ── Layout ── */
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 0 40px;
        }}

        /* ── Section headings ── */
        .section {{
            margin-top: 52px;
        }}
        .section-heading {{
            display: flex; align-items: center; gap: 12px;
            margin-bottom: 24px;
        }}
        .section-heading h2 {{
            font-size: 20px; font-weight: 600; letter-spacing: -0.01em;
        }}
        .section-line {{
            flex: 1; height: 1px;
            background: linear-gradient(90deg, var(--border), transparent);
        }}

        /* ── Topic Cards ── */
        .topics-grid {{
            display: flex; flex-direction: column; gap: 10px;
        }}
        .topic-card {{
            display: flex; gap: 16px; align-items: flex-start;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 20px;
            transition: border-color 0.2s, transform 0.2s;
        }}
        .topic-card:hover {{
            border-color: rgba(124,58,237,0.3);
            transform: translateX(3px);
        }}
        .topic-rank {{
            font-size: 12px; font-weight: 700;
            color: var(--muted);
            min-width: 28px;
            margin-top: 3px;
        }}
        .topic-body {{ flex: 1; min-width: 0; }}
        .topic-badge {{
            display: inline-block;
            font-size: 10px; font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            padding: 2px 8px;
            border-radius: 100px;
            margin-bottom: 6px;
        }}
        .topic-title {{
            display: block;
            color: var(--text);
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 4px;
            transition: color 0.2s;
        }}
        .topic-title:hover {{ color: #a78bfa; }}
        .topic-snippet {{
            font-size: 12px; color: var(--muted);
            line-height: 1.5; margin-bottom: 6px;
        }}
        .topic-stats {{
            display: flex; gap: 14px;
            font-size: 12px; color: var(--muted);
        }}

        /* ── Draft Cards ── */
        .drafts-grid {{ display: flex; flex-direction: column; gap: 20px; }}
        .draft-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-left: 3px solid var(--accent);
            border-radius: 14px;
            padding: 28px;
            transition: box-shadow 0.2s, border-color 0.2s;
            position: relative;
        }}
        .draft-card:hover {{
            box-shadow: 0 0 30px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.06);
        }}
        .draft-header {{
            display: flex; align-items: flex-start; gap: 16px;
            margin-bottom: 20px;
        }}
        .draft-icon {{
            font-size: 28px;
            flex-shrink: 0;
            width: 52px; height: 52px;
            display: flex; align-items: center; justify-content: center;
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            border-radius: 12px;
        }}
        .draft-title {{
            font-size: 17px; font-weight: 600;
            color: #fff;
            margin-bottom: 4px;
        }}
        .draft-inspiration {{
            font-size: 12px; color: var(--muted);
            font-style: italic;
            line-height: 1.5;
        }}
        .copy-btn {{
            margin-left: auto;
            flex-shrink: 0;
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            color: var(--muted);
            font-family: inherit;
            font-size: 13px;
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s, color 0.2s, border-color 0.2s;
        }}
        .copy-btn:hover {{
            background: rgba(124,58,237,0.15);
            border-color: rgba(124,58,237,0.4);
            color: #a78bfa;
        }}
        .copy-btn.copied {{
            background: rgba(16,185,129,0.15);
            border-color: rgba(16,185,129,0.4);
            color: #10b981;
        }}
        .draft-post {{
            background: rgba(0,0,0,0.3);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px 22px;
            font-size: 15px;
            line-height: 1.75;
            color: var(--text);
            white-space: pre-wrap;
            word-break: break-word;
        }}

        /* ── Footer ── */
        .footer {{
            margin-top: 64px;
            text-align: center;
            color: var(--muted);
            font-size: 12px;
            opacity: 0.5;
        }}

        /* ── Responsive ── */
        @media (max-width: 600px) {{
            .header {{ padding: 32px 20px; }}
            .container {{ padding: 0 20px; }}
            .draft-header {{ flex-wrap: wrap; }}
            .copy-btn {{ margin-left: 0; width: 100%; justify-content: center; }}
        }}
    </style>
</head>
<body>

<div class="header">
    <div class="header-inner">
        <div class="header-eyebrow">
            <span class="header-pill">🎮 LinkedIn Weekly</span>
            <span class="header-dot"></span>
            <span style="font-size:12px;color:#64748b">Live</span>
        </div>
        <h1>Your Weekly Post Drafts</h1>
        <p class="header-meta">Generated {date_str} at {time_str} · Ready for your review &amp; light editing</p>
        <div class="header-stats">
            <div class="stat">
                <div>
                    <div class="stat-num">{len(top_content)}</div>
                    <div class="stat-label">Trending topics</div>
                </div>
            </div>
            <div class="stat">
                <div>
                    <div class="stat-num">{NUM_DRAFTS}</div>
                    <div class="stat-label">Draft posts</div>
                </div>
            </div>
            <div class="stat">
                <div>
                    <div class="stat-num">6</div>
                    <div class="stat-label">Sources scanned</div>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="container">

    <div class="section">
        <div class="section-heading">
            <h2>🔥 This Week's Trending Topics</h2>
            <div class="section-line"></div>
        </div>
        <div class="topics-grid">
            {topics_html}
        </div>
    </div>

    <div class="section">
        <div class="section-heading">
            <h2>✍️ Your Draft Posts</h2>
            <div class="section-line"></div>
        </div>
        <p style="color:var(--muted);font-size:13px;margin-bottom:20px;">
            Pick one, give it a personal touch, then paste it into LinkedIn. Hit 📋 Copy to grab the text instantly.
        </p>
        <div class="drafts-grid">
            {drafts_html}
        </div>
    </div>

</div>

<div class="footer">
    <p>Generated by LinkedIn Weekly Post Generator · Powered by Claude AI</p>
</div>

<script>
    function copyDraft(btn, text) {{
        navigator.clipboard.writeText(text).then(() => {{
            btn.textContent = '✅ Copied!';
            btn.classList.add('copied');
            setTimeout(() => {{
                btn.textContent = '📋 Copy';
                btn.classList.remove('copied');
            }}, 2500);
        }}).catch(() => {{
            // Fallback for older browsers
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            btn.textContent = '✅ Copied!';
            btn.classList.add('copied');
            setTimeout(() => {{
                btn.textContent = '📋 Copy';
                btn.classList.remove('copied');
            }}, 2500);
        }});
    }}
</script>

</body>
</html>"""

    return html


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("  🎮  LinkedIn Weekly Post Generator")
    print("  " + "─" * 38)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print()
        print("  ❌  Error: ANTHROPIC_API_KEY not set.")
        print("      Copy .env.example to .env and add your key.")
        print("      Get one at: https://console.anthropic.com/settings/keys")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Fetch ──
    print()
    print("  📡  Fetching trending content...")
    all_posts: list[dict] = []
    all_posts.extend(fetch_reddit_posts(REDDIT_SUBREDDITS))
    all_posts.extend(fetch_hackernews_posts())
    all_posts.extend(fetch_gamasutra_posts())

    if not all_posts:
        print()
        print("  ❌  No posts fetched — check your internet connection.")
        sys.exit(1)

    print(f"\n  📊  Total collected: {len(all_posts)} posts")

    # ── Rank ──
    top_content = rank_content(all_posts)
    print(f"  🏆  Top {len(top_content)} ranked by engagement score")

    # ── Draft ──
    print()
    print(f"  ✍️   Generating drafts with {CLAUDE_MODEL}...")
    try:
        drafts_data = generate_drafts(top_content, api_key)
        num_drafts = len(drafts_data.get("drafts", []))
        print(f"  ✓   {num_drafts} draft posts generated")
    except json.JSONDecodeError as exc:
        print(f"  ❌  {CLAUDE_MODEL} returned invalid JSON: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"  ❌  {CLAUDE_MODEL} error: {exc}")
        sys.exit(1)

    # ── Render ──
    run_date = datetime.datetime.now()
    html_content = render_html_report(top_content, drafts_data, run_date)

    filename = run_date.strftime("%Y-%m-%d") + "_linkedin_weekly.html"
    output_path = OUTPUT_DIR / filename
    output_path.write_text(html_content, encoding="utf-8")

    print()
    print(f"  ✅  Report saved:")
    print(f"      {output_path}")
    print()
    print("  🌐  Opening in browser...")
    subprocess.Popen(f'start "" "{output_path}"', shell=True)
    print()
    print("  Done! Pick a draft, tweak it, and post. 🚀")
    print()


if __name__ == "__main__":
    main()
