"""
sector_returns.py
セクター資金フロー可視化用のデータ生成。

各セクターETFの調整後終値(トータルリターン近似)を yfinance で取得し、
- 各期間リターン(1d/7d/1m/3m/6m/12m。7d=直近5営業日)
- 直近12ヶ月の日次終値系列(折れ線の正規化はフロント側で実施)
- 上位/下位から自動生成した相場観サマリー
を quartz/static/sector-returns-<market>.json に出力する(§5.3 スキーマ)。

取得失敗時は前回JSONを据え置き(stale)。GitHub Actions で毎日更新する想定。

実行:
  python sector_returns.py --market us  --out quartz/static/sector-returns-us.json
  python sector_returns.py --market jp  --out quartz/static/sector-returns-jp.json
"""

from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys
import time
import numpy as np
import pandas as pd

HISTORY_MONTHS = 12          # 折れ線で使う保持期間
FETCH_PERIOD = "2y"          # 12ヶ月リターン+余裕をみて長めに取得

# (表示名, ETFティッカー)。yfinanceのティッカーは US=そのまま, JP=コード.T
MARKETS = {
    "us": {
        "currency": "USD",
        "sectors": [
            ("情報技術", "XLK"), ("コミュニケーション", "XLC"), ("一般消費財", "XLY"),
            ("生活必需品", "XLP"), ("ヘルスケア", "XLV"), ("金融", "XLF"),
            ("資本財", "XLI"), ("エネルギー", "XLE"), ("素材", "XLB"),
            ("公益", "XLU"), ("不動産", "XLRE"),
        ],
    },
    "jp": {
        "currency": "JPY",
        "sectors": [
            ("食品", "1617"), ("エネルギー資源", "1618"), ("建設・資材", "1619"),
            ("素材・化学", "1620"), ("医薬品", "1621"), ("自動車・輸送機", "1622"),
            ("鉄鋼・非鉄", "1623"), ("機械", "1624"), ("電機・精密", "1625"),
            ("情報通信・サービス", "1626"), ("電力・ガス", "1627"), ("運輸・物流", "1628"),
            ("商社・卸売", "1629"), ("小売", "1630"), ("銀行", "1631"),
            ("金融(除く銀行)", "1632"), ("不動産", "1633"),
        ],
    },
}

# 期間 -> 概算カレンダー日数(終値系列から直近営業日を引く)
PERIOD_DAYS = {"1m": 30, "3m": 91, "6m": 182, "12m": 365}


def yf_ticker(market: str, etf: str) -> str:
    return f"{etf}.T" if market == "jp" else etf


def fetch_closes(ticker: str, retries: int = 3) -> pd.Series:
    """調整後終値(auto_adjust=True)= トータルリターン近似。一過性失敗はリトライ。"""
    import yfinance as yf
    last = None
    for attempt in range(retries):
        try:
            px = yf.download(ticker, period=FETCH_PERIOD, auto_adjust=True, progress=False)["Close"]
            s = px.squeeze("columns") if isinstance(px, pd.DataFrame) else px
            s = s.dropna()
            if not s.empty:
                return s
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.2 * (attempt + 1))
    if last:
        raise last
    raise RuntimeError(f"{ticker}: empty series")


def pct_at_offset(s: pd.Series, days: int) -> float | None:
    """最新終値 vs 「days カレンダー日前以前の直近営業日」終値 の騰落率(%)。"""
    last_date = s.index[-1]
    target = last_date - pd.Timedelta(days=days)
    prior = s.loc[:target]
    if prior.empty:
        return None
    return round(float(s.iloc[-1] / prior.iloc[-1] - 1) * 100, 2)


def pct_at_bdays(s: pd.Series, n: int) -> float | None:
    """最新終値 vs n営業日前 の騰落率(%)。1d=1, 7d(=5営業日)=5。"""
    if len(s) <= n:
        return None
    return round(float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 2)


def build_sector(name: str, etf: str, s: pd.Series) -> dict:
    returns = {
        "1d": pct_at_bdays(s, 1),
        "7d": pct_at_bdays(s, 5),                  # 7d = 直近5営業日
        "1m": pct_at_offset(s, PERIOD_DAYS["1m"]),
        "3m": pct_at_offset(s, PERIOD_DAYS["3m"]),
        "6m": pct_at_offset(s, PERIOD_DAYS["6m"]),
        "12m": pct_at_offset(s, PERIOD_DAYS["12m"]),
    }
    # 直近12ヶ月の日次終値([date, close])
    cutoff = s.index[-1] - pd.DateOffset(months=HISTORY_MONTHS)
    recent = s.loc[s.index >= cutoff]
    closes = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in recent.items()]
    return {"name": name, "etf": etf, "returns": returns, "closes": closes}


def make_summary(sectors: list[dict]) -> str:
    """1ヶ月リターンの上位/下位から一言サマリーを生成。"""
    ranked = [x for x in sectors if x["returns"].get("1m") is not None]
    if not ranked:
        return "データ取得中です。"
    ranked.sort(key=lambda x: x["returns"]["1m"], reverse=True)
    top, bottom = ranked[0], ranked[-1]
    return (f"{top['name']}が月間首位（{top['returns']['1m']:+.1f}%）。"
            f"{bottom['name']}が最下位（{bottom['returns']['1m']:+.1f}%）。")


def _load_prev(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def validate(doc: dict) -> list[str]:
    errs = []
    for k in ("updated", "currency", "summary", "sectors"):
        if k not in doc:
            errs.append(f"missing {k}")
    if not doc.get("sectors"):
        errs.append("sectors empty")
    for sec in doc.get("sectors", []):
        for k in ("name", "etf", "returns", "closes"):
            if k not in sec:
                errs.append(f"{sec.get('etf','?')}: missing {k}")
    return errs


def emit(market: str, out_path: str) -> int:
    cfg = MARKETS[market]
    path = Path(out_path)
    prev = _load_prev(path)

    sectors, ok = [], 0
    for name, etf in cfg["sectors"]:
        try:
            s = fetch_closes(yf_ticker(market, etf))
            sectors.append(build_sector(name, etf, s))
            ok += 1
            print(f"  {etf} {name}: 1d={sectors[-1]['returns']['1d']} 1m={sectors[-1]['returns']['1m']} pts={len(sectors[-1]['closes'])}")
        except Exception as e:  # noqa: BLE001
            print(f"  skip {etf} {name}: {e}")

    # 全滅 or 半分以上失敗なら据え置き(stale)
    if ok < max(3, len(cfg["sectors"]) // 2):
        if prev is not None:
            print(">> 取得不足。前回JSONを据え置き、上書きしません。")
            return 0
        print(">> 取得不足かつ前回値なし。", file=sys.stderr)
        return 1

    doc = {
        "updated": sectors and sectors[0]["closes"][-1][0] or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "currency": cfg["currency"],
        "summary": make_summary(sectors),
        "sectors": sectors,
    }
    errs = validate(doc)
    if errs:
        print(">> スキーマ検証失敗:", "; ".join(errs), file=sys.stderr)
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">> 書き出し: {path}  (sectors={len(sectors)} / {cfg['currency']})")
    print(f"   summary: {doc['summary']}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="セクター資金フロー データ生成")
    ap.add_argument("--market", choices=["us", "jp"], required=True)
    ap.add_argument("--out", default=None, help="省略時は quartz/static/sector-returns-<market>.json")
    args = ap.parse_args()
    out = args.out or f"quartz/static/sector-returns-{args.market}.json"
    sys.exit(emit(args.market, out))
