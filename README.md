# 半導體 & AI 科技供應鏈日報 | Daily Tech Supply Chain Report

每天自動抓取 19 家半導體與科技公司最新資訊，依供應鏈三層架構分類，
透過 Claude AI 整理成繁體中文簡報（含每日三大重點），寄送到指定 Gmail 信箱。

---

## 覆蓋範圍（供應鏈三層架構）

| 層級 | 類別 | 公司 |
|------|------|------|
| 🔬 上游 | 半導體設備 | ASML、Applied Materials (AMAT)、Lam Research (LRCX)、KLA (KLAC)、Tokyo Electron (8035.T) |
| 💡 中游 | 晶片設計製造 | TSMC (TSM)、Samsung (005930.KS)、SK Hynix (000660.KS)、Micron (MU)、Intel (INTC)、NVIDIA (NVDA)、AMD、Broadcom (AVGO)、MediaTek (2454.TW)、Marvell (MRVL) |
| ☁️ 下游 | 雲端超大規模 | Amazon/AWS (AMZN)、Microsoft (MSFT)、Meta (META)、Alphabet (GOOGL) |

---

## 設定步驟（10 分鐘完成）

### Step 1 — Fork 這個 Repo

在 GitHub 上 fork 此 repo 到你自己的帳號。

### Step 2 — 取得三個必要的金鑰

#### A. Anthropic API Key
1. 前往 https://console.anthropic.com
2. Settings → API Keys → Create Key
3. 複製備用

#### B. Gmail App Password（非 Gmail 登入密碼）
1. 前往 https://myaccount.google.com/security
2. 開啟「兩步驟驗證」（若尚未開啟）
3. 搜尋「應用程式密碼」→ 建立新的
4. 選擇「郵件」+ 裝置名稱（例如 GitHub Actions）
5. 複製 16 位元密碼（格式：xxxx xxxx xxxx xxxx）

#### C. 確認寄件 Gmail 帳號
預設收件人已設定為 `perrylu21@gmail.com`。
寄件人使用你自己的 Gmail（下方設定為 `GMAIL_USER`）。

### Step 3 — 設定 GitHub Secrets

在你 fork 的 repo：
**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名稱 | 值 |
|---|---|
| `ANTHROPIC_API_KEY` | sk-ant-... |
| `GMAIL_USER` | your.email@gmail.com |
| `GMAIL_APP_PASSWORD` | 16 位元應用程式密碼 |

### Step 4 — 啟用 Actions

前往 **Actions** 頁籤 → 點擊 **Enable GitHub Actions**。

### Step 5 — 測試執行

**Actions → Daily Tech & Semiconductor Report → Run workflow**

幾分鐘後應收到第一封報告信。

---

## 排程時間

預設：**週一至週五，台灣時間 08:30**（UTC 00:30）

修改 `.github/workflows/daily_report.yml` 中的 cron expression：

```yaml
# 每天（含週末）08:30 台灣時間
- cron: "30 0 * * *"

# 週一至週五 07:00 台灣時間
- cron: "0 23 * * 0-4"
```

Cron 時間參考：https://crontab.guru

---

## 費用估算

| 服務 | 費用 |
|------|------|
| GitHub Actions | 免費（公開 repo）或每月 2,000 分鐘免費 |
| Anthropic API | 約 $0.02–0.05 USD / 封信（claude-opus-4-5） |
| Google News RSS | 免費 |
| Yahoo Finance (yfinance) | 免費 |

每月費用約 **$0.50–1.50 USD**。

---

## 自訂設定

### 修改覆蓋的股票

編輯 `src/generate_report.py` 中的 `TICKERS` 字典：

```python
TICKERS = {
    "TSM":  "TSMC (台積電)",
    "NVDA": "NVIDIA",
    # 新增任何 Yahoo Finance 支援的代碼
    "ASML": "ASML",
    "INTC": "Intel",
}
```

### 修改收件人

```python
RECIPIENT_EMAIL = "your-email@example.com"
```

### 切換為英文報告

在 `generate_report()` 函數中，將 prompt 語言指示從繁體中文改為英文。

---

## 故障排除

| 問題 | 解法 |
|------|------|
| Email 未收到 | 確認 App Password 正確（不是 Gmail 登入密碼） |
| Actions 未觸發 | 確認 repo 有 commit activity（GitHub 有時暫停閒置 repo 的排程） |
| 股價顯示 N/A | Yahoo Finance 可能暫時不可用；yfinance 會自動重試 |
| API 錯誤 | 確認 `ANTHROPIC_API_KEY` secret 正確設定 |

---

## 本機測試

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."
export GMAIL_USER="your@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"

python src/generate_report.py
```
