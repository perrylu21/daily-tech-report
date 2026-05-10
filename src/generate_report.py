"""
Daily Tech & Semiconductor Report Generator
Fetches news + stock prices, generates AI report, sends via Gmail
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

TICKERS = {
    "TSM":  "TSMC (台積電)",
    "NVDA": "NVIDIA",
    "AMD":  "AMD",
    "AVGO": "Broadcom",
    "AMZN": "Amazon / AWS",
    "GOOGL":"Alphabet / Google",
    "META": "Meta",
}

NEWS_QUERIES = [
    "TSMC semiconductor advanced packaging",
    "NVIDIA GPU AI chips",
    "AMD semiconductor earnings",
    "Broadcom AVGO networking",
    "Amazon AWS cloud revenue",
    "Google Alphabet AI cloud",
    "Meta AI infrastructure",
]

# ── Stock Data ───────────────────────────────────────────────────────────────

def fetch_stock_prices() -> dict:
    prices = {}
    symbols = list(TICKERS.keys())
    try:
        data = yf.download(symbols, period="2d", interval="1d", progress=False, threads=True)
        close = data["Close"]
        for sym in symbols:
            try:
                today_price = float(close[sym].iloc[-1])
                prev_price  = float(close[sym].iloc[-2])
                change_pct  = (today_price - prev_price) / prev_price * 100
                prices[sym] = {
                    "price":      f"${today_price:.2f}",
                    "change_pct": f"{change_pct:+.2f}%",
                    "direction":  "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                    "name":       TICKERS[sym],
                }
            except Exception as e:
                prices[sym] = {"price": "N/A", "change_pct": "N/A", "direction": "flat", "name": TICKERS[sym]}
    except Exception as e:
        print(f"[WARN] yfinance batch failed: {e}")
        for sym in symbols:
            prices[sym] = {"price": "N/A", "change_pct": "N/A", "direction": "flat", "name": TICKERS[sym]}
    return prices

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
                    "title":   entry.get("title", ""),
                    "summary": entry.get("summary", "")[:300],
                    "link":    entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] News fetch failed for '{query}': {e}")
    return articles

# ── AI Report Generation ─────────────────────────────────────────────────────

def generate_report(stock_data: dict, news_articles: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = today.strftime("%Y年%m月%d日 %A")

    stock_lines = "\n".join(
        f"  {sym}: {v['price']} ({v['change_pct']})" for sym, v in stock_data.items()
    )

    news_block = ""
    for i, a in enumerate(news_articles[:20], 1):
        news_block += f"{i}. [{a['title']}]\n   {a['summary']}\n   {a['published']}\n\n"

    prompt = f"""你是頂尖半導體與科技股分析師。請根據以下資料，以繁體中文撰寫今日每日簡報。

今日日期：{date_str}（台灣時間）

──── 今日收盤股價 ────
{stock_lines}

──── 最新新聞摘要（過去24-48小時）────
{news_block}

請按以下結構輸出報告（全部繁體中文）：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 每日科技半導體簡報 | {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【執行摘要】
（3句話，涵蓋今日市場最重要訊號）

【雲端超大規模業者】

▌Amazon / AWS
• 最新動態（2-3點）
• 分析師觀點

▌Google / Alphabet
• 最新動態（2-3點）
• 分析師觀點

▌Meta
• 最新動態（2-3點）
• 分析師觀點

【半導體】

▌TSMC（台積電）
• 最新動態（2-3點，聚焦先進製程/CoWoS/AI晶片需求）
• 分析師觀點

▌NVIDIA
• 最新動態（2-3點，聚焦GPU/AI基礎設施）
• 分析師觀點

▌AMD
• 最新動態（2-3點）
• 分析師觀點

▌Broadcom
• 最新動態（2-3點，聚焦網路/AI ASIC）
• 分析師觀點

【跨板塊市場觀察】
（2-3個本週值得關注的產業結構趨勢）

【今日股價一覽】
{stock_lines}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 本報告由 Claude AI 自動生成，僅供研究參考，不構成投資建議。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── HTML Email Template ──────────────────────────────────────────────────────

def build_html_email(report_text: str, stock_data: dict) -> str:
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    date_str = today.strftime("%Y年%m月%d日")

    def stock_row(sym, v):
        color = "#1a7a4a" if v["direction"] == "up" else "#c0392b" if v["direction"] == "down" else "#555"
        arrow = "▲" if v["direction"] == "up" else "▼" if v["direction"] == "down" else "─"
        return f"""
        <tr>
          <td style="padding:6px 12px;font-weight:600;color:#1a1a2e;">{sym}</td>
          <td style="padding:6px 12px;color:#333;">{v['name']}</td>
          <td style="padding:6px 12px;font-weight:600;color:#1a1a2e;">{v['price']}</td>
          <td style="padding:6px 12px;color:{color};font-weight:600;">{arrow} {v['change_pct']}</td>
        </tr>"""

    stock_rows = "".join(stock_row(s, v) for s, v in stock_data.items())

    # Convert plain text report to HTML paragraphs
    html_body = report_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html_body = html_body.replace("\n\n", "</p><p style='margin:0 0 10px;line-height:1.8;'>")
    html_body = html_body.replace("\n", "<br>")
    html_body = f"<p style='margin:0 0 10px;line-height:1.8;'>{html_body}</p>"

    # Style section headers
    for marker in ["【執行摘要】","【雲端超大規模業者】","【半導體】","【跨板塊市場觀察】","【今日股價一覽】"]:
        html_body = html_body.replace(
            marker,
            f'<h2 style="font-size:15px;font-weight:700;color:#1a1a2e;border-left:4px solid #2e4057;padding-left:10px;margin:20px 0 8px;">{marker}</h2>'
        )
    for marker in ["▌Amazon / AWS","▌Google / Alphabet","▌Meta","▌TSMC（台積電）","▌NVIDIA","▌AMD","▌Broadcom"]:
        html_body = html_body.replace(
            marker,
            f'<h3 style="font-size:13px;font-weight:700;color:#2e4057;margin:14px 0 6px;">{marker}</h3>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:#1a1a2e;padding:28px 32px;">
    <div style="font-size:11px;color:#8899aa;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px;">Daily Intelligence Briefing</div>
    <div style="font-size:22px;font-weight:700;color:#ffffff;">📊 科技半導體日報</div>
    <div style="font-size:13px;color:#aabbcc;margin-top:6px;">{date_str} · Powered by Claude AI</div>
  </td></tr>

  <!-- Stock table -->
  <tr><td style="padding:24px 32px 0;">
    <div style="font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">今日收盤股價</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e8eaed;border-radius:6px;overflow:hidden;font-size:13px;">
      <tr style="background:#f8f9fa;">
        <th style="padding:8px 12px;text-align:left;color:#555;font-weight:600;font-size:11px;">代碼</th>
        <th style="padding:8px 12px;text-align:left;color:#555;font-weight:600;font-size:11px;">公司</th>
        <th style="padding:8px 12px;text-align:left;color:#555;font-weight:600;font-size:11px;">股價</th>
        <th style="padding:8px 12px;text-align:left;color:#555;font-weight:600;font-size:11px;">漲跌</th>
      </tr>
      {stock_rows}
    </table>
  </td></tr>

  <!-- Report body -->
  <tr><td style="padding:24px 32px;font-size:13px;color:#333;line-height:1.8;">
    {html_body}
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f8f9fa;padding:16px 32px;border-top:1px solid #e8eaed;">
    <div style="font-size:11px;color:#999;line-height:1.6;">
      此報告由 Claude AI 自動生成，資料來源包含 Google News、Yahoo Finance。<br>
      僅供研究參考，不構成投資建議。如需取消訂閱，請回覆此信件。
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
    subject = f"📊 每日科技半導體簡報 {date_str}"

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
    print("[1/4] Fetching stock prices…")
    stock_data = fetch_stock_prices()
    for sym, v in stock_data.items():
        print(f"  {sym}: {v['price']} ({v['change_pct']})")

    print("[2/4] Fetching news…")
    news_articles = fetch_news(max_per_query=3)
    print(f"  Fetched {len(news_articles)} articles")

    print("[3/4] Generating AI report…")
    report_text = generate_report(stock_data, news_articles)
    print(f"  Generated {len(report_text)} chars")

    print("[4/4] Sending email…")
    html = build_html_email(report_text, stock_data)
    send_email(html, report_text)
    print("[DONE]")

if __name__ == "__main__":
    main()
