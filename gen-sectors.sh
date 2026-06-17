#!/usr/bin/env bash
# セクター資金フロー用の実データを生成して quartz/static/ に書き出す。
set -e
cd "$(dirname "$0")"
python3 sector_returns.py --market us
python3 sector_returns.py --market jp
