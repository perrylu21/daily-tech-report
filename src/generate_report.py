"""
Daily Tech & Semiconductor Report Generator — Supply Chain Edition
三層供應鏈架構：上游設備 → 中游晶片 → 下游雲端
Fetches stock prices + news, generates AI report, sends via Gmail
"""

import os
import json
import smtplib
import datetime
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import yfinance as yf
import feedparser
import requests

# ── Config ──────────────────────────────────────────────────────────────────

RECIPIENT_EMAIL = "perrylu21@gmail.com"
SENDER_EMAIL    = os.environ["GMAIL_USER"]
GMAIL_APP_PASS  = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_KEY   = os.environ["ANTHROPIC_API_KEY"]

# ── Three-Tier Supply Chain Structure ────────────────────────────────────────
#
# 上游 (Upstream)  — Semiconductor Equipment
# 中游 (Midstream) — Chip Design & Manufacturing
# 下游 (Downstream)— Cloud Hyperscalers
#
# Each entry: ticker → (display_name, currency_symbol, tier)

TICKERS = {
    # ── 上游：半導體設備 ─────────────────────────────────────────────────────
    "ASML":      ("ASML Holding",            "$",    "upstream"),
    "AMAT":      ("Applied Materials",        "$",    "upstream"),
    "LRCX":      ("Lam Research",             "$",    "upstream"),
    "KLAC":      ("KLA Corporation",          "$",    "upstream"),
    "8035.T":    ("Tokyo Electron 東京威力科創", "¥",    "upstream"),

    # ── 中游：晶片設計製造 ───────────────────────────────────────────────────
    "TSM":       ("TSMC 台積電 (ADR)",         "$",    "midstream"),
    "005930.KS": ("Samsung Electronics 三星",  "₩",    "midstream"),
    "000660.KS": ("SK Hynix",                 "₩",    "midstream"),
    "MU":        ("Micron Technology",         "$",    "midstream"),
    "INTC":      ("Intel Corporation",         "$",    "midstream"),
    "NVDA":      ("NVIDIA Corporation",        "$",    "midstream"),
    "AMD":       ("Advanced Micro Devices",    "$",    "midstream"),
    "AVGO":      ("Broadcom Inc.",             "$",    "midstream"),
    "2454.TW":   ("MediaTek 聯發科",           "NT$",  "midstream"),
    "MRVL":      ("Marvell Technology",        "$",    "midstream"),

    # ── 下游：雲端超大規模業者 ───────────────────────────────────────────────
    "AMZN":      ("Amazon / AWS",             "$",    "downstream"),
    "MSFT":      ("Microsoft / Azure",        "$",    "downstream"),
    "META":      ("Meta Platforms",           "$",    "downstream"),
    "GOOGL":     ("Alphabet / Google",        "$",    "downstream"),
}

TIER_META = {
    "upstream":   {"label": "🔬 上游（Upstream）— 半導體設備", "companies": "ASML · AMAT · Lam Research · KLA · Tokyo Electron"},
    "midstream":  {"label": "💡 中游（Midstream）— 晶片設計製造", "companies": "TSMC · Samsung · SK Hynix · Micron · Intel · NVIDIA · AMD · Broadcom · MediaTek · Marvell"},
    "downstream": {"label": "☁️ 下游（Downstream）— 雲端超大規模", "companies": "Amazon/AWS · Microsoft · Meta · Alphabet"},
}

# ── News Queries ─────────────────────────────────────────────────────────────

NEWS_QUERIES = [
    # 上游設備
    "ASML EUV lithography export control semiconductor",
    "Applied Materials AMAT semiconductor equipment AI chips",
    "Lam Research KLA semiconductor equipment earnings",
    "Tokyo Electron TEL semiconductor China export",
    # 中游晶片
    "TSMC advanced packaging CoWoS AI chip demand",
    "Samsung SK Hynix HBM memory AI chip",
    "Micron HBM4 memory revenue earnings",
    "Intel foundry 18A AI chip manufacturing",
    "NVIDIA GPU Blackwell AI data center",
    "AMD Instinct MI300 AI accelerator",
    "Broadcom AVGO AI ASIC custom chip",
    "MediaTek Marvell AI chip ASIC",
    # 下游雲端
    "Amazon AWS Bedrock AI agent cloud",
    "Microsoft Azure Copilot AI OpenAI",
    "Meta Llama AI infrastructure spending",
    "Google Alphabet Gemini DeepMind AI cloud",
]

# ── Stock Data ───────────────────────────────────────────────────────────────

def fetch_stock_prices() -> dict:
    """Fetch latest close price + daily change for all tickers."""
    prices = {}
    symbols = list(TICKERS.keys())

    # yfinance batch download
    try:
        data = yf.download(symbols, period="5d", interval="1d", progress=False, threads=True)
        close = data["Close"]
        for sym in symbols:
            currency, tier = TICKERS[sym][1], TICKERS[sym][2]
            try:
                series = close[sym].dropna()
                today_price = float(series.iloc[-1])
                prev_price  = float(series.iloc[-2])
                change_pct  = (today_price - prev_price) / prev_price * 100
                # Format price based on currency magnitude
                if currency in ("₩",):
                    price_str = f"{currency}{today_price:,.0f}"
                elif currency == "¥":
                    price_str = f"{currency}{today_price:,.0f}"
                else:
                    price_str = f"{currency}{today_price:.2f}"
                prices[sym] = {
                    "name":       TICKERS[sym][0],
                    "currency":   currency,
                    "tier":       tier,
                    "price":      price_str,
                    "price_raw":  today_price,
                    "change_pct": f"{change_pct:+.2f}%",
                    "direction":  "up" if change_pct > 0 else ("down" if change_pct < 0 else "flat"),
                }
            except Exception as e:
                prices[sym] = {
                    "name": TICKERS[sym][0], "currency": TICKERS[sym][1],
                    "tier": TICKERS[sym][2], "price": "N/A",
                    "price_raw": 0, "change_pct": "N/A", "direction": "flat",
                }
    except Exception as e:
        print(f"[WARN] yfinance batch failed: {e}")
        for sym in symbols:
            prices[sym] = {
                "name": TICKERS[sym][0], "currency": TICKERS[sym][1],
                "tier": TICKERS[sym][2], "price": "N/A",
                "price_raw": 0, "change_pct": "N/A", "direction": "flat",
            }
    return prices


def format_stock_block(prices: dict) -> str:
    """Return plain-text stock summary grouped by tier, for the AI prompt."""
    lines = []
    for tier_key in ("upstream", "midstream", "downstream"):
        lines.append(f"\n── {TIER_META[tier_key]['label']} ──")
        for sym, v in prices.items():
            if v["tier"] == tier_key:
                lines.append(f"  {sym:12s} {v['name']:35s} {v['price']:>12}  {v['change_pct']}")
    return "\n".join(lines)

# ── News via Google News RSS ─────────────────────────────────────────────────

def fetch_news(max_per_query: int = 3) -> list[dict]:
    articles = []
    base_url = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    for query in NEWS_QUERIES:
        try:
            url  = base_url.format(query=requests.utils.quote(query))
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_query]:
                articles.append({
                    "title":     entry.get("title", ""),
                    "summary":   entry.get("summary", "")[:300],
                    "link":      entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
            time.sleep(0.4)
        except Exception as e:
            print(f"[WARN] News fetch failed for '{query}': {e}")
    return articles

# ── AI Report Generation ─────────────────────────────────────────────────────

def generate_report(stock_data: dict, news_articles: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = today.strftime("%Y年%m月%d日 %A")

    stock_block = format_stock_block(stock_data)

    news_block = ""
    for i, a in enumerate(news_articles[:30], 1):
        news_block += f"{i}. [{a['title']}]\n   {a['summary']}\n   {a['published']}\n\n"

    prompt = f"""你是頂尖半導體與科技股分析師。請根據以下股價與新聞資料，以繁體中文撰寫今日每日簡報。

今日日期：{date_str}（台灣時間）

──── 今日股價（依供應鏈三層架構分類）────
{stock_block}

──── 最新新聞摘要（過去 24-48 小時）────
{news_block}

請嚴格按以下結構輸出報告（全部繁體中文）：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 半導體 & AI 科技供應鏈日報 | {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【每日三大重點 · Daily Executive Summary】
① （最重要的市場訊號，1-2句，點名具體公司與數字）
② （第二重要訊號，1-2句，點名具體公司與數字）
③ （第三重要訊號，1-2句，點名具體公司與數字）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【🔬 上游（Upstream）— 半導體設備】
ASML · AMAT · Lam Research · KLA · Tokyo Electron
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▌ASML
• 最新動態（2點，聚焦 EUV 出貨、出口管制、客戶動向）

▌AMAT（Applied Materials）
• 最新動態（2點）

▌Lam Research ／ KLA
• 最新動態（合併2點，聚焦設備需求、中國市場）

▌Tokyo Electron（東京威力科創）
• 最新動態（2點，聚焦中國佔比、日本政策）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【💡 中游（Midstream）— 晶片設計製造】
TSMC · Samsung · SK Hynix · Micron · Intel · NVIDIA · AMD · Broadcom · MediaTek · Marvell
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▌TSMC（台積電）
• 最新動態（2-3點，聚焦先進製程、CoWoS、AI晶片需求、漲價）

▌Samsung ／ SK Hynix
• 最新動態（2-3點，聚焦 HBM、記憶體週期、市值）

▌Micron
• 最新動態（2點，聚焦 HBM4、營收財測）

▌Intel
• 最新動態（2點，聚焦 18A 代工、AI 佈局、股價動能）

▌NVIDIA
• 最新動態（2-3點，聚焦 GPU/Blackwell、資料中心、財務）

▌AMD
• 最新動態（2點，聚焦 MI系列 AI加速器、市佔）

▌Broadcom
• 最新動態（2點，聚焦 AI ASIC、定制晶片客戶、財測）

▌MediaTek（聯發科）／ Marvell
• 最新動態（2點，聚焦 ASIC 戰略、邊緣AI）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【☁️ 下游（Downstream）— 雲端超大規模業者】
Amazon/AWS · Microsoft · Meta · Alphabet
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▌Amazon / AWS
• 最新動態（2-3點，聚焦 Bedrock、AI Agent、資本支出）

▌Microsoft / Azure
• 最新動態（2-3點，聚焦 Copilot、自研模型、OpenAI關係）

▌Meta
• 最新動態（2點，聚焦 Llama、AI基礎建設）

▌Alphabet / Google
• 最新動態（2-3點，聚焦 Gemini、DeepMind、Google Cloud）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【📡 跨板塊市場觀察】
（2-3個本週值得關注的供應鏈結構趨勢或地緣政治風險）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 本報告由 Claude AI 自動生成，僅供研究參考，不構成投資建議。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── HTML Email Template ──────────────────────────────────────────────────────

TIER_COLORS = {
    "upstream":   "#6d28d9",   # purple
    "midstream":  "#0369a1",   # blue
    "downstream": "#047857",   # green
}

def build_html_email(report_text: str, stock_data: dict) -> str:
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = today.strftime("%Y年%m月%d日")

    # ── Stock table rows, grouped by tier ──
    def stock_row(sym, v, stripe):
        bg     = "#fafafa" if stripe else "#ffffff"
        color  = "#15803d" if v["direction"] == "up" else ("#b91c1c" if v["direction"] == "down" else "#555")
        arrow  = "▲" if v["direction"] == "up" else ("▼" if v["direction"] == "down" else "─")
        dot    = f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{TIER_COLORS[v["tier"]]};margin-right:6px;"></span>'
        return f"""
        <tr style="background:{bg};">
          <td style="padding:6px 10px;font-weight:700;color:#1a1a2e;font-size:12px;white-space:nowrap;">{dot}{sym}</td>
          <td style="padding:6px 10px;color:#444;font-size:12px;">{v['name']}</td>
          <td style="padding:6px 10px;font-weight:700;color:#1a1a2e;font-size:12px;text-align:right;white-space:nowrap;">{v['price']}</td>
          <td style="padding:6px 10px;font-weight:700;color:{color};font-size:12px;text-align:right;white-space:nowrap;">{arrow} {v['change_pct']}</td>
        </tr>"""

    def tier_header_row(label, color):
        return f"""
        <tr>
          <td colspan="4" style="padding:6px 10px;background:{color};color:#fff;font-size:10px;font-weight:800;letter-spacing:0.5px;text-transform:uppercase;">{label}</td>
        </tr>"""

    stock_rows_html = ""
    stripe = False
    for tier_key, tier_info in TIER_META.items():
        stock_rows_html += tier_header_row(tier_info["label"], TIER_COLORS[tier_key])
        for sym, v in stock_data.items():
            if v["tier"] == tier_key:
                stock_rows_html += stock_row(sym, v, stripe)
                stripe = not stripe

    # ── Convert plain text report to styled HTML ──
    html_body = report_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_body = html_body.replace("\n\n", "</p><p style='margin:0 0 10px;line-height:1.85;font-size:13px;color:#333;'>")
    html_body = html_body.replace("\n", "<br>")
    html_body = f"<p style='margin:0 0 10px;line-height:1.85;font-size:13px;color:#333;'>{html_body}</p>"

    # Style section headers
    section_headers = [
        "【每日三大重點 · Daily Executive Summary】",
        "【🔬 上游（Upstream）— 半導體設備】",
        "【💡 中游（Midstream）— 晶片設計製造】",
        "【☁️ 下游（Downstream）— 雲端超大規模業者】",
        "【📡 跨板塊市場觀察】",
    ]
    for h in section_headers:
        html_body = html_body.replace(
            h,
            f'<h2 style="font-size:14px;font-weight:800;color:#1a1a2e;border-left:4px solid #2e4057;'
            f'padding-left:10px;margin:24px 0 8px;letter-spacing:-0.2px;">{h}</h2>'
        )

    # Style company sub-headers
    company_headers = [
        "▌ASML", "▌AMAT（Applied Materials）", "▌Lam Research ／ KLA",
        "▌Tokyo Electron（東京威力科創）", "▌TSMC（台積電）",
        "▌Samsung ／ SK Hynix", "▌Micron", "▌Intel", "▌NVIDIA",
        "▌AMD", "▌Broadcom", "▌MediaTek（聯發科）／ Marvell",
        "▌Amazon / AWS", "▌Microsoft / Azure", "▌Meta", "▌Alphabet / Google",
    ]
    for ch in company_headers:
        html_body = html_body.replace(
            ch,
            f'<h3 style="font-size:13px;font-weight:700;color:#2e4057;margin:14px 0 5px;">{ch}</h3>'
        )

    # Style the 3 exec summary bullets
    for prefix in ["①", "②", "③"]:
        html_body = html_body.replace(
            prefix,
            f'<span style="display:inline-block;background:#f59e0b;color:#fff;font-weight:800;'
            f'font-size:11px;width:20px;height:20px;border-radius:50%;text-align:center;'
            f'line-height:20px;margin-right:6px;">{prefix}</span>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#eef0f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef0f4;padding:20px 0;">
<tr><td align="center">
<table width="700" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:#0a0a1a;padding:26px 30px;">
    <div style="font-size:11px;color:#6b7280;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:5px;">Daily Intelligence Briefing · Supply Chain Edition</div>
    <div style="font-size:21px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">📊 半導體 &amp; AI 科技供應鏈日報</div>
    <div style="font-size:12px;color:#9ca3af;margin-top:5px;">{date_str}（台灣時間）· Powered by Claude AI</div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
      <span style="background:#6d28d9;color:#fff;font-size:10px;font-weight:700;padding:3px 9px;border-radius:20px;">🔬 上游設備 ×5</span>
      <span style="background:#0369a1;color:#fff;font-size:10px;font-weight:700;padding:3px 9px;border-radius:20px;">💡 中游晶片 ×10</span>
      <span style="background:#047857;color:#fff;font-size:10px;font-weight:700;padding:3px 9px;border-radius:20px;">☁️ 下游雲端 ×4</span>
    </div>
  </td></tr>

  <!-- Stock Table -->
  <tr><td style="padding:22px 28px 0;">
    <div style="font-size:10px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px;">今日股價一覽 · Stock Snapshot</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;font-size:12px;">
      <tr style="background:#f9fafb;">
        <th style="padding:7px 10px;text-align:left;color:#6b7280;font-weight:700;font-size:10px;text-transform:uppercase;">代碼</th>
        <th style="padding:7px 10px;text-align:left;color:#6b7280;font-weight:700;font-size:10px;text-transform:uppercase;">公司</th>
        <th style="padding:7px 10px;text-align:right;color:#6b7280;font-weight:700;font-size:10px;text-transform:uppercase;">股價</th>
        <th style="padding:7px 10px;text-align:right;color:#6b7280;font-weight:700;font-size:10px;text-transform:uppercase;">漲跌</th>
      </tr>
      {stock_rows_html}
    </table>
    <div style="font-size:10px;color:#9ca3af;margin-top:5px;">
      <span style="color:#6d28d9;">●</span> 上游設備 &nbsp;
      <span style="color:#0369a1;">●</span> 中游晶片 &nbsp;
      <span style="color:#047857;">●</span> 下游雲端
    </div>
  </td></tr>

  <!-- Report Body -->
  <tr><td style="padding:20px 28px;">
    {html_body}
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f9fafb;padding:14px 28px;border-top:1px solid #e5e7eb;">
    <div style="font-size:10px;color:#9ca3af;line-height:1.7;">
      此報告由 Claude AI 自動生成，資料來源包含 Google News RSS、Yahoo Finance (yfinance)。<br>
      覆蓋 19 家公司 | 上游設備 5 家 · 中游晶片 10 家 · 下游雲端 4 家 | 僅供研究參考，不構成投資建議。
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

# ── Send Email ───────────────────────────────────────────────────────────────

def send_email(html_content: str, report_text: str):
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = today.strftime("%Y/%m/%d")
    subject = f"📊 半導體供應鏈日報 [上游/中游/下游] {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL

    msg.attach(MIMEText(report_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, GMAIL_APP_PASS)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
    print(f"[OK] Email sent to {RECIPIENT_EMAIL}")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("[1/4] Fetching stock prices (19 tickers across 3 tiers)…")
    stock_data = fetch_stock_prices()
    for sym, v in stock_data.items():
        print(f"  [{v['tier']:10s}] {sym:12s} {v['price']:>12}  {v['change_pct']}")

    print("[2/4] Fetching news…")
    news_articles = fetch_news(max_per_query=3)
    print(f"  Fetched {len(news_articles)} articles from {len(NEWS_QUERIES)} queries")

    print("[3/4] Generating AI report (three-tier supply chain format)…")
    report_text = generate_report(stock_data, news_articles)
    print(f"  Generated {len(report_text)} chars")

    print("[4/4] Sending email…")
    html = build_html_email(report_text, stock_data)
    send_email(html, report_text)
    print("[DONE]")

if __name__ == "__main__":
    main()
