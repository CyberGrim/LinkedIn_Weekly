# LinkedIn Weekly Post Generator

Stay top of mind in your professional network with a weekly LinkedIn post — without spending hours thinking of ideas.

This script scrapes trending topics from game dev and programming communities, then uses AI to draft 3 casual, punchy LinkedIn posts ready for your review.

## Setup (one-time)

### 1. Install Python dependencies

```powershell
cd d:\code\Git-Repos\linkedin-weekly
pip install -r requirements.txt
```

### 2. Get an Anthropic API key

1. Go to [https://console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
2. Create an API key (billing must be enabled on your Anthropic account)
3. Copy it

### 3. Create your `.env` file

```powershell
Copy-Item .env.example .env
```

Then open `.env` and replace `your_anthropic_api_key_here` with your actual key.

---

## Running the script

Each week, open a terminal and run:

```powershell
cd d:\code\Git-Repos\linkedin-weekly
python linkedin_weekly.py
```

The report will open automatically in your browser. Reports are saved to:
```
reports\YYYY-MM-DD_linkedin_weekly.html
```

---

## What it does

1. **Fetches** trending posts from:
   - r/gamedev, r/indiegaming, r/programming, r/cscareerquestions
   - Hacker News (game/dev relevant stories)
   - Game Developer Magazine RSS

2. **Ranks** content by engagement (upvotes + comments × 3)

3. **Generates** 3 distinct LinkedIn post drafts via Claude (`claude-haiku-4-5`):
   - Casual, fun, light-hearted tone
   - Short and punchy (3–5 sentences)
   - Different hooks and angles each time

4. **Opens** a beautiful HTML report in your browser with:
   - This week's top trending topics with links
   - All 3 draft posts with one-click copy buttons

---

## Sources

| Source | What it provides |
|---|---|
| r/gamedev | Game dev discussion & pain points |
| r/indiegaming | Indie community trends |
| r/programming | General programming pulse |
| r/cscareerquestions | Career & industry news |
| Hacker News | Tech industry stories |
| Game Developer Magazine | Industry news & analysis |
