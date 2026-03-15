#!/usr/bin/env bash
# SHATTERED Dogfooding Eval Script
# Tests real shard endpoints against live data on Legion
# 30+ checks across infrastructure, documents, entities, search, LLM, and analysis shards
set -euo pipefail

BASE="${SHATTERED_URL:-http://localhost:8100}"
PASS=0
FAIL=0
TOTAL=0

check() {
    local name="$1" url="$2" expected="$3"
    TOTAL=$((TOTAL + 1))
    local response
    response=$(curl -sf "$url" 2>/dev/null) || { echo "  FAIL [$name] — connection error"; FAIL=$((FAIL + 1)); return; }

    if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); $expected" 2>/dev/null; then
        echo "  PASS [$name]"
        PASS=$((PASS + 1))
    else
        echo "  FAIL [$name] — assertion failed"
        FAIL=$((FAIL + 1))
    fi
}

check_post() {
    local name="$1" url="$2" data="$3" expected="$4"
    TOTAL=$((TOTAL + 1))
    local response
    response=$(curl -sf -X POST "$url" -H "Content-Type: application/json" -d "$data" 2>/dev/null) || { echo "  FAIL [$name] — connection error"; FAIL=$((FAIL + 1)); return; }

    if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); $expected" 2>/dev/null; then
        echo "  PASS [$name]"
        PASS=$((PASS + 1))
    else
        echo "  FAIL [$name] — assertion failed"
        FAIL=$((FAIL + 1))
    fi
}

# check_exists: endpoint returns valid JSON (not 404/500) — empty lists are OK
check_exists() {
    local name="$1" url="$2"
    TOTAL=$((TOTAL + 1))
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null) || { echo "  FAIL [$name] — connection error"; FAIL=$((FAIL + 1)); return; }

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 400 ]; then
        # Also verify it returns valid JSON
        local response
        response=$(curl -sf "$url" 2>/dev/null) || { echo "  FAIL [$name] — could not fetch body"; FAIL=$((FAIL + 1)); return; }
        if echo "$response" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
            echo "  PASS [$name] (HTTP $http_code)"
            PASS=$((PASS + 1))
        else
            echo "  FAIL [$name] — not valid JSON (HTTP $http_code)"
            FAIL=$((FAIL + 1))
        fi
    else
        echo "  FAIL [$name] — HTTP $http_code"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== SHATTERED Dogfooding Eval ==="
echo "Target: $BASE"
echo "Checks: 30+"
echo ""

# ─────────────────────────────────────────────
echo "--- 1. Health & Infrastructure ---"
check "health_status"    "$BASE/api/health" "assert d['status'] == 'healthy'"
check "shards_count"     "$BASE/api/health" "assert len(d['frame']['shards']) >= 47"
check "services_all_up"  "$BASE/api/health" "assert all(d['frame']['services'].values())"

# ─────────────────────────────────────────────
echo ""
echo "--- 2. Documents ---"
check "doc_count"        "$BASE/api/documents/count" "assert d['count'] >= 2000"
check "doc_stats"        "$BASE/api/documents/stats"  "assert d['total_documents'] >= 2000"
check "doc_chunks_exist" "$BASE/api/documents/stats"  "assert d.get('total_chunks', d.get('total_documents', 0)) > 0"

# ─────────────────────────────────────────────
echo ""
echo "--- 3. Entities ---"
check "entities_exist"        "$BASE/api/entities/items?limit=5"  "assert len(d['items']) >= 1"
check "entities_person"       "$BASE/api/entities/items?limit=50" "assert any('Griffiths' in e['name'] for e in d['items'])"
check "entities_type_person"  "$BASE/api/entities/items?limit=100" "assert any(e.get('entity_type','').upper() == 'PERSON' for e in d['items'])"
check "entities_type_org"     "$BASE/api/entities/items?limit=100" "assert any(e.get('entity_type','').upper() == 'ORGANIZATION' for e in d['items'])"

# ─────────────────────────────────────────────
echo ""
echo "--- 4. Timeline ---"
check "timeline_docs"   "$BASE/api/timeline/documents?limit=5" "assert len(d['documents']) >= 1"
check "timeline_events" "$BASE/api/timeline/events?limit=5"    "assert isinstance(d.get('events', d.get('items', [])), list)"

# ─────────────────────────────────────────────
echo ""
echo "--- 5. Search ---"
check_post "keyword_discrimination" "$BASE/api/search/keyword" '{"query":"discrimination","limit":3}' "assert d['total'] > 0 and len(d['items']) > 0"
check_post "keyword_griffiths"      "$BASE/api/search/keyword" '{"query":"Stuart Griffiths","limit":3}' "assert len(d['items']) > 0"
check_post "keyword_harassment"     "$BASE/api/search/keyword" '{"query":"harassment victimisation","limit":3}' "assert len(d['items']) > 0"

# ─────────────────────────────────────────────
echo ""
echo "--- 6. LLM ---"
check "llm_available"  "$BASE/api/dashboard/llm" "assert d['available'] == True"
check "llm_model"      "$BASE/api/dashboard/llm" "assert 'qwen' in d['model'].lower() or 'gemma' in d['model'].lower()"
check "llm_not_grok"   "$BASE/api/dashboard/llm" "assert 'grok' not in d['model'].lower()"
check "llm_not_claude" "$BASE/api/dashboard/llm" "assert 'claude' not in d['model'].lower()"
check "llm_not_gpt"    "$BASE/api/dashboard/llm" "assert 'gpt' not in d['model'].lower()"
check_post "llm_test_call" "$BASE/api/dashboard/llm/test" '{}' "assert d['success'] == True"

# ─────────────────────────────────────────────
echo ""
echo "--- 7. Dashboard ---"
check "db_stats" "$BASE/api/dashboard/database/stats" "assert d['connected'] == True"

# ─────────────────────────────────────────────
echo ""
echo "--- 8. Deduplication ---"
check "dedup_stats" "$BASE/api/documents/deduplication/stats" "assert d['total_documents'] >= 2000"

# ─────────────────────────────────────────────
echo ""
echo "--- 9. Analysis Shards (endpoint wiring) ---"
check_exists "ach_matrices"       "$BASE/api/ach/matrices"
check_exists "burden_map_items"   "$BASE/api/burden-map/items"
check_exists "claims_items"       "$BASE/api/claims/items"
check_exists "contradictions_items" "$BASE/api/contradictions/items"
check_exists "credibility_items"  "$BASE/api/credibility/items"
check_exists "crossexam_items"    "$BASE/api/crossexam/items"
check_exists "deadlines_items"    "$BASE/api/deadlines/items"
check_exists "disclosure_items"   "$BASE/api/disclosure/items"
check_exists "strategist_items"   "$BASE/api/strategist/items"
check_exists "sentiment_items"    "$BASE/api/sentiment/items"
check_exists "patterns_items"     "$BASE/api/patterns/items"
check_exists "respondent_intel"   "$BASE/api/respondent-intel/items"
check_exists "witnesses_items"    "$BASE/api/witnesses/items"
check_exists "letters_items"      "$BASE/api/letters/items"
check_exists "reports_items"      "$BASE/api/reports/items"
check_exists "settings_items"     "$BASE/api/settings/items"

# ─────────────────────────────────────────────
echo ""
echo "=== RESULTS: $PASS passed, $FAIL failed, $TOTAL total ==="
if [ "$FAIL" -eq 0 ]; then
    echo "ALL PASS"
    exit 0
else
    echo "SOME FAILURES"
    exit 1
fi
