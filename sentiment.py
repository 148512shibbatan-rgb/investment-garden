"""
sentiment.py
日米株センチメント指数(0-100 / 5段階)— 同一エンジン・等加重・パーセンタイル正規化

設計
----
1. 性質の違うレイヤーから1指標ずつ拾う
2. 各指標 → 過去N営業日窓のパーセンタイル(0-100)に変換(単位を消す)
3. 符号を「高い=浮かれ(強欲)」に統一 → 等加重平均
4. 0-100 を 5段階に割り当て
5. JP / US を同じ物差しで別々に出し、補助で平均した GLOBAL を3本目に置く

データ層
--------
US: VIX・HYスプレッドは FRED の fredgraph.csv で無料取得(APIキー不要)。
    SPXモメンタム・株債リターン差は yfinance。Put/Call のみ CSV を置く。
JP: USD/JPY・日経VI代理(N225実現ボラ)・N225 125日線乖離は yfinance(全自動)。

実行
----
  python sentiment.py                                  # デモ(コンソール出力。実データ→不足なら合成)
  python sentiment.py --emit-json quartz/static/sentiment.json   # JSON出力(実データのみ。サイト用)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys
import time
import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# 設定(最初に決める3つ:窓 / 平滑化 / 最低本数)
# ----------------------------------------------------------------------
WINDOW = 504        # 正規化窓(営業日)≒ 2年
MIN_PERIODS = 252   # スコア開始に必要な最低日数 ≒ 1年
SMOOTH = 5          # 合成スコアの平滑化(営業日)
MIN_INDICATORS = 3  # この本数以上揃った日だけスコアを出す
HISTORY_MAX = 90    # sentiment.json の history 末尾保持件数
DATA_DIR = Path("data")

BANDS = [
    (0,   20,  "①悲壮"),
    (20,  40,  "②弱気"),
    (40,  60,  "③中立"),
    (60,  80,  "④強気"),
    (80, 101,  "⑤浮かれ"),
]
# JSON用の素のラベル(band 1-5)
BAND_LABELS = {1: "悲壮", 2: "弱気", 3: "中立", 4: "強気", 5: "浮かれ"}


@dataclass
class Indicator:
    name: str
    invert: bool   # True = 生値が高いほど恐怖 → 反転して「高スコア=強欲」に統一
    label: str


# ----------------------------------------------------------------------
# 市場別の指標セット
#   JP: スクレイピング依存指標(騰落レシオ等)は外し、yfinanceで全自動取得できる3本に割り切り
#   US: FRED + yfinance の5本(put_call のみ任意CSV)
# ----------------------------------------------------------------------
MARKETS: dict[str, list[Indicator]] = {
    "JP": [
        Indicator("nikkei_vi",      True,  "日経VI(代理)"),
        Indicator("n225_mom125",    False, "日経225 vs 125日線"),
        Indicator("usdjpy_mom20",   False, "USD/JPY 20日モメンタム"),
    ],
    "US": [
        Indicator("vix",            True,  "VIX"),
        Indicator("hy_oas",         True,  "ハイイールドOAS"),
        Indicator("spx_mom125",     False, "S&P500 vs 125日線"),
        Indicator("stocks_vs_bonds",False, "株 vs 債 20日リターン差"),
        Indicator("put_call",       True,  "Put/Call レシオ"),
    ],
}


# ----------------------------------------------------------------------
# エンジン(=「物差し化」本体。JP/US共通。既存実装を流用)
# ----------------------------------------------------------------------
def to_business_daily(s: pd.Series) -> pd.Series:
    s = s.sort_index().dropna()
    idx = pd.bdate_range(s.index.min(), s.index.max())
    return s.reindex(idx).ffill()


def rolling_greed_pct(s: pd.Series, invert: bool,
                      window: int = WINDOW, min_periods: int = MIN_PERIODS) -> pd.Series:
    x = -s if invert else s
    return x.rolling(window, min_periods=min_periods).rank(pct=True) * 100.0


def build_index(raw: dict[str, pd.Series], indicators: list[Indicator],
                weights: dict[str, float] | None = None,
                smooth: int = SMOOTH) -> pd.DataFrame:
    use = [ind for ind in indicators if ind.name in raw]
    daily = {ind.name: to_business_daily(raw[ind.name].astype(float)) for ind in use}
    pct = pd.DataFrame({ind.name: rolling_greed_pct(daily[ind.name], ind.invert) for ind in use})

    if weights is None:                       # 等加重スタート
        composite = pct.mean(axis=1, skipna=True)
    else:
        w = pd.Series(weights).reindex(pct.columns).fillna(0.0)
        composite = (pct * w).sum(axis=1, skipna=True) / pct.notna().mul(w).sum(axis=1)

    valid = pct.notna().sum(axis=1)
    composite = composite.where(valid >= MIN_INDICATORS).rolling(smooth, min_periods=1).mean()

    out = pct.copy()
    out["composite"] = composite
    out["band"] = composite.map(to_band)
    out["n_indicators"] = valid
    return out


def to_band(v):
    if pd.isna(v):
        return None
    for lo, hi, label in BANDS:
        if lo <= v < hi:
            return label
    return BANDS[-1][2]


def band_num(score) -> int | None:
    """0-100スコア → band番号(1-5)。"""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return None
    return int(min(int(score // 20) + 1, 5))


def global_index(jp_out: pd.DataFrame, us_out: pd.DataFrame) -> pd.DataFrame:
    """JP・USの合成スコアを等加重平均した補助指標(乖離は潰さず別途残す)。"""
    g = pd.concat([jp_out["composite"], us_out["composite"]], axis=1, keys=["JP", "US"]).dropna()
    comp = g.mean(axis=1)
    return pd.DataFrame({"JP": g["JP"], "US": g["US"], "composite": comp, "band": comp.map(to_band)})


# ----------------------------------------------------------------------
# データ層(CSVキャッシュ優先 / 取得可能なものだけ自動fetch)
# ----------------------------------------------------------------------
def load_from_csv(name: str) -> pd.Series | None:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=[0], index_col=0)
    return df.iloc[:, 0]


def fred_series(series_id: str, retries: int = 4) -> pd.Series:
    """FREDの公開CSV(APIキー不要)。欠損は '.' なので coerce で除去。
    FREDは一過性で 504 等を返すことがあるため指数バックオフでリトライする。"""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    last = None
    for attempt in range(retries):
        try:
            df = pd.read_csv(url)
            df.columns = ["date", "value"]
            s = pd.to_numeric(df["value"], errors="coerce")
            s.index = pd.to_datetime(df["date"])
            return s.dropna()
        except Exception as e:  # noqa: BLE001 — 504/接続失敗をまとめてリトライ
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def _yf_close(ticker: str, period: str = "6y") -> pd.Series:
    import yfinance as yf
    px = yf.download(ticker, period=period, auto_adjust=True, progress=False)["Close"]
    return px.squeeze("columns") if isinstance(px, pd.DataFrame) else px


# --- US fetchers ---
def fetch_vix():
    """まず FRED VIXCLS。FRED不達(504等)のときは Yahoo の ^VIX(同じCBOE VIX指数)へフォールバック。"""
    try:
        return fred_series("VIXCLS").rename("vix")
    except Exception as e:
        print(f"  note vix: FRED不達({e}) → yfinance ^VIX にフォールバック")
        return _yf_close("^VIX").rename("vix")

def fetch_hy_oas():     return fred_series("BAMLH0A0HYM2").rename("hy_oas")

def fetch_spx_mom125():
    px = _yf_close("^GSPC")
    return ((px / px.rolling(125).mean() - 1) * 100).rename("spx_mom125")

def fetch_stocks_vs_bonds():
    spx = _yf_close("^GSPC").pct_change(20)
    bond = _yf_close("IEF").pct_change(20)       # 7-10年米国債ETF
    return ((spx - bond) * 100).rename("stocks_vs_bonds")

# --- JP fetchers ---
def fetch_usdjpy_mom20():
    px = _yf_close("JPY=X")
    return (px.pct_change(20) * 100).rename("usdjpy_mom20")

def fetch_nikkei_vi_proxy():
    """本物の日経VIが無いとき: N225の20日実現ボラ(年率%)。向きはVIと同じ。"""
    px = _yf_close("^N225")
    ret = np.log(px).diff()
    return (ret.rolling(20).std() * np.sqrt(252) * 100).rename("nikkei_vi")

def fetch_n225_mom125():
    """N225 終値 ÷ 125日線 − 1 (%)。モメンタム。"""
    px = _yf_close("^N225")
    return ((px / px.rolling(125).mean() - 1) * 100).rename("n225_mom125")


FETCHERS = {
    "vix": fetch_vix, "hy_oas": fetch_hy_oas,
    "spx_mom125": fetch_spx_mom125, "stocks_vs_bonds": fetch_stocks_vs_bonds,
    "usdjpy_mom20": fetch_usdjpy_mom20,
    "nikkei_vi": fetch_nikkei_vi_proxy, "n225_mom125": fetch_n225_mom125,
}

# CSV必須(無料APIが無い)指標と取得元の目安
CSV_HINTS = {
    "put_call":    "CBOE 総合Put/Call(代替: AAII強気弱気スプレッド)",
    "toraku_25":   "騰落レシオ → 株探 / みんかぶ",
    "margin_pl":   "信用評価損益率(週次)→ 松井証券 / JPX",
    "short_ratio": "空売り比率(日次)→ JPX公表",
}


def load_indicator(name: str) -> pd.Series:
    s = load_from_csv(name)
    if s is not None:
        return s
    if name in FETCHERS:
        return FETCHERS[name]()
    hint = CSV_HINTS.get(name, "")
    raise FileNotFoundError(f"[{name}] data/{name}.csv(列: date,value)が必要。 {hint}")


def load_market(market: str) -> dict[str, pd.Series]:
    raw = {}
    for ind in MARKETS[market]:
        try:
            raw[ind.name] = load_indicator(ind.name)
        except Exception as e:
            print(f"  skip {market}/{ind.name}: {e}")
    return raw


# ----------------------------------------------------------------------
# JSON出力(サイト用。§5スキーマ準拠。実データのみ。失敗市場は前回値流用=stale)
# ----------------------------------------------------------------------
def _market_block(market: str) -> tuple[dict, str] | None:
    """実データから1市場分のブロックを作る。不足なら None。戻り値は (block, as_of)。"""
    inds = MARKETS[market]
    raw = load_market(market)
    if sum(1 for k in raw if not raw[k].dropna().empty) < MIN_INDICATORS:
        return None
    out = build_index(raw, inds)
    sub = out.dropna(subset=["composite"])
    if sub.empty:
        return None
    latest = sub.iloc[-1]
    score = round(float(latest["composite"]), 1)
    bnum = band_num(score)
    components = []
    for ind in inds:
        v = latest.get(ind.name, np.nan)
        if pd.notna(v):
            components.append({
                "name": ind.name, "label": ind.label,
                "percentile": round(float(v), 1), "invert": ind.invert,
            })
    history = [
        {"date": idx.date().isoformat(), "score": round(float(val), 1)}
        for idx, val in sub["composite"].tail(HISTORY_MAX).items()
    ]
    block = {
        "score": score, "band": bnum, "band_label": BAND_LABELS[bnum],
        "n_indicators": int(latest["n_indicators"]), "stale": False,
        "components": components, "history": history,
    }
    return block, sub.index[-1].date().isoformat()


def _load_prev(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def emit_json(path_str: str) -> int:
    path = Path(path_str)
    prev = _load_prev(path)
    markets: dict[str, dict] = {}
    as_ofs: list[str] = []
    fresh = 0

    for m in ("JP", "US"):
        res = _market_block(m)
        if res is not None:
            block, as_of = res
            markets[m] = block
            as_ofs.append(as_of)
            fresh += 1
            print(f"  {m}: score={block['score']} band={block['band']}({block['band_label']}) "
                  f"n={block['n_indicators']} as_of={as_of}")
        elif prev and m in prev.get("markets", {}):
            block = dict(prev["markets"][m])
            block["stale"] = True
            markets[m] = block
            if prev.get("as_of"):
                as_ofs.append(prev["as_of"])
            print(f"  {m}: 取得不足 → 前回値を流用(stale=true)")
        else:
            print(f"  {m}: 取得不足かつ前回値なし → この市場は省略")

    # 全市場とも新規取得できず、前回JSONがあるなら据え置き(サイトを空白にしない)
    if fresh == 0 and prev is not None:
        print(">> 全市場で新規取得に失敗。前回の sentiment.json を据え置き、上書きしません。")
        return 0

    if "JP" in markets and "US" in markets:
        jp, us = markets["JP"]["score"], markets["US"]["score"]
        g = round((jp + us) / 2, 1)
        gb = band_num(g)
        markets["GLOBAL"] = {
            "score": g, "band": gb, "band_label": BAND_LABELS[gb], "jp": jp, "us": us,
        }
    elif prev and "GLOBAL" in prev.get("markets", {}):
        markets["GLOBAL"] = prev["markets"]["GLOBAL"]

    doc = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": max(as_ofs) if as_ofs else (prev.get("as_of") if prev else None),
        "markets": markets,
    }

    errors = validate_doc(doc)
    if errors:
        print(">> スキーマ検証に失敗。JSONを書き出しません:", "; ".join(errors), file=sys.stderr)
        return 1

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">> 書き出し: {path}  (markets={list(markets)})")
    return 0


def validate_doc(doc: dict) -> list[str]:
    """§5スキーマの軽量バリデーション。必須キー存在・score範囲・band整合。"""
    errs: list[str] = []
    for k in ("schema_version", "generated_at", "as_of", "markets"):
        if k not in doc:
            errs.append(f"top:missing {k}")
    for m in ("JP", "US"):
        if m not in doc.get("markets", {}):
            continue  # 省略は許容(stale運用)
        b = doc["markets"][m]
        for k in ("score", "band", "band_label", "n_indicators", "stale", "components", "history"):
            if k not in b:
                errs.append(f"{m}:missing {k}")
        if "score" in b and not (0 <= b["score"] <= 100):
            errs.append(f"{m}:score out of range {b['score']}")
        if "band" in b and b["band"] not in (1, 2, 3, 4, 5):
            errs.append(f"{m}:band invalid {b['band']}")
    return errs


# ----------------------------------------------------------------------
# 表示(デモ用)
# ----------------------------------------------------------------------
def report(out: pd.DataFrame, indicators: list[Indicator], title: str, tail: int = 8):
    sub = out.dropna(subset=["composite"])
    if sub.empty:
        print(f"[{title}] スコア算出に必要なデータが不足しています。")
        return
    latest = sub.iloc[-1]
    n_total = len(indicators)
    print("=" * 62)
    print(f"{title}  {out.index[-1].date()}")
    print(f"  スコア: {latest['composite']:5.1f}/100  →  {latest['band']}"
          f"   (採用 {int(latest['n_indicators'])}/{n_total})")
    print("-" * 62)
    for ind in indicators:
        v = latest.get(ind.name, np.nan)
        if not pd.isna(v):
            print(f"    {v:5.1f}  {ind.label}")
    print("=" * 62)


# ----------------------------------------------------------------------
# デモ(合成データ)
# ----------------------------------------------------------------------
def _synthetic(indicators, seed=7, n=900):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    fear = np.zeros(n)
    for t in range(1, n):
        fear[t] = 0.97 * fear[t - 1] + rng.normal(0, 1)
    fear = (fear - fear.mean()) / fear.std()
    raw = {}
    for ind in indicators:
        sign = +1 if ind.invert else -1     # invert指標は恐怖で上昇
        base, scale = 20, 6
        raw[ind.name] = pd.Series(base + sign * scale * fear
                                  + rng.normal(0, scale * 0.3, n), index=idx)
    return raw


def run(market: str, use_real: bool = True) -> pd.DataFrame:
    inds = MARKETS[market]
    raw = load_market(market) if use_real else {}
    if len([k for k in raw if not raw[k].dropna().empty]) < MIN_INDICATORS:
        print(f">> {market}: 実データ不足。合成デモにフォールバック。")
        raw = _synthetic(inds, seed=hash(market) % 100)
    out = build_index(raw, inds)
    report(out, inds, f"{market} センチメント指数")
    return out


def demo():
    jp = run("JP", use_real=True)
    print()
    us = run("US", use_real=True)
    print()
    g = global_index(jp, us)
    if not g.dropna().empty:
        last = g.dropna().iloc[-1]
        print("=" * 62)
        print(f"GLOBAL(JP・US等加重)  {g.dropna().index[-1].date()}")
        print(f"  スコア: {last['composite']:5.1f}/100  →  {last['band']}"
              f"    (JP {last['JP']:.1f} / US {last['US']:.1f})")
        print("=" * 62)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="日米株センチメント指数")
    ap.add_argument("--emit-json", metavar="PATH",
                    help="実データから sentiment.json を出力(例: quartz/static/sentiment.json)")
    args = ap.parse_args()
    if args.emit_json:
        sys.exit(emit_json(args.emit_json))
    else:
        demo()
