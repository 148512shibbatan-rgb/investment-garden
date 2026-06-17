#!/usr/bin/env bash
# GitHub Actions から呼ぶ: セクター実データを生成し、変化があれば commit & push。
set -e
pip install -r requirements.txt
python3 sector_returns.py --market us
python3 sector_returns.py --market jp
git config user.name github-actions
git config user.email actions@github.com
git add quartz/static/sector-returns-us.json quartz/static/sector-returns-jp.json
git commit -m "chore(sectors): update sector-returns [skip ci]" || echo "no change"
git push
