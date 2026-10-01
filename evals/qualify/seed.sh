#!/usr/bin/env bash
# solstice-fixture: synthetic (seeds one invented, scored candidate for the qualify eval)
#
# Usage: SOLSTICE_WORKSPACE=<scratch workspace> ./seed.sh [run-a|run-b]
# Every number is copied from a page in fixture-market/ through the manual
# adapter, so it enters through `solstice demand fetch` like any other number.
# Prints the problem ID on the last line.
set -euo pipefail

: "${SOLSTICE_WORKSPACE:?set SOLSTICE_WORKSPACE to a scratch workspace made by solstice init}"
variant="${1:-run-a}"
M="http://127.0.0.1:8766"
here="$(cd "$(dirname "$0")" && pwd)"
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

pid=$(solstice demand fetch manual --query "auction lot watch extension" \
  --metric extension_users --value 12000 --unit users \
  --url "$M/store/example-lot-tracker.html" --source "Example Extension Store" \
  --new-problem --title "Collectors miss auction lot closings across several auction sites" \
  | json 'd["problem"]["id"]')

add() {  # metric value unit url source
  solstice demand fetch manual --query "auction lot watch extension" --metric "$1" --value "$2" \
    --unit "$3" --url "$4" --source "$5" --problem "$pid" >/dev/null
}
add sales_count 1150 sales "$M/store/example-lot-tracker.html" "Example Extension Store"
add keyword_volume 1900 searches_per_month "$M/keywords/auction-lot-watch-extension.html" "Example Keyword Tool"
add trend_change_pct 34 percent "$M/keywords/auction-lot-watch-extension.html" "Example Keyword Tool"

if [ "$variant" = "run-b" ]; then
  quote2="Is there a watcher that covers more than one auction site? I would happily pay monthly."
else
  quote2=$(python3 - "$here/fixture-market/forum/lot-watch-2.html" <<'PY'
import re, sys
html = open(sys.argv[1]).read()
print(re.search(r"<article><p>(.*?)</p></article>", html, re.S).group(1))
PY
)
fi

evidence() {  # url summary quote
  python3 -c '
import json, sys
url, summary, quote, pid = sys.argv[1:5]
print(json.dumps({"problem_id": pid, "kind": "complaint", "url": url,
                  "fetched_at": "2026-09-20T10:00:00Z", "adapter": "web", "method": "scrape",
                  "summary": summary, "data": {"quote": quote}}))' "$1" "$2" "$3" "$pid" \
  | solstice record create evidence --file - | json 'd["id"]'
}
ev1=$(evidence "$M/forum/lot-watch-1.html" "A collector who pays for a one-site watcher wants all sites covered." \
  "I track lots on four auction sites and keep missing closings. The one extension I pay for only covers one site.")
ev2=$(evidence "$M/forum/lot-watch-2.html" "A collector asks for a multi-site watcher and would pay monthly." "$quote2")

solstice record update problem "$pid" --file - >/dev/null <<EOF
{"lens": "marketplace_gap", "shape": "extension", "slug": "example-lot-watch",
 "summary": "Collectors watch lots on several auction sites; the paid incumbent covers one site.",
 "evidence_ids": ["$ev1", "$ev2"]}
EOF

entries=$(solstice record get problem "$pid" | json '" ".join(e["id"] for e in d["demand"])')
read -r users sales volume trend <<<"$entries"
solstice score "$pid" --ratings - >/dev/null <<EOF
{"spend": {"anchor": 0.75, "citations": ["$sales"]},
 "channel_reach": {"anchor": 0.75, "citations": ["$users"]},
 "gap": {"anchor": 0.75, "citations": ["$ev1", "$ev2"]},
 "pain": {"anchor": 0.75, "citations": ["$ev1"]}}
EOF
echo "$pid"
