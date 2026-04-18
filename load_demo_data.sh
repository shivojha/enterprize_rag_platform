#!/bin/bash
# Ingest all demo loan documents into the RAG pipeline
set -e

API="http://localhost:8002"
DATA="./sample_data"

echo "================================"
echo " Loading Demo Mortgage Data"
echo "================================"

ingest() {
  local LOAN_ID=$1
  local DOC_TYPE=$2
  local FILE=$3
  echo "  → $LOAN_ID / $DOC_TYPE"
  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API/ingest/$LOAN_ID?doc_type=$DOC_TYPE" -F "file=@$FILE")
  BODY=$(echo "$RESPONSE" | head -n -1)
  CODE=$(echo "$RESPONSE" | tail -n 1)
  if [ "$CODE" = "200" ] && [ -n "$BODY" ]; then
    JOB=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('job_id','?')[:8])" 2>/dev/null || echo "?")
    echo "    ✓ queued (job: $JOB)"
  else
    echo "    ✗ failed (HTTP $CODE): $BODY"
  fi
}

status_check() {
  RESPONSE=$(curl -s -w "\n%{http_code}" "$API/loans/$1/status")
  BODY=$(echo "$RESPONSE" | head -n -1)
  CODE=$(echo "$RESPONSE" | tail -n 1)
  if [ "$CODE" = "200" ] && [ -n "$BODY" ]; then
    echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
docs = d.get('documents', [])
summary = ', '.join(f\"{x['doc_type']}({x['status']}:{x.get('chunks',0)}chunks)\" for x in docs)
print(f'  {d[\"loan_id\"]}: {summary or \"no docs yet\"}')
" 2>/dev/null || echo "  $1: parse error"
  else
    echo "  $1: HTTP $CODE"
  fi
}

echo ""
echo "[LN-2024-001] John Smith — Application Submitted"
ingest "LN-2024-001" "application" "$DATA/LN-2024-001/application.txt"

echo ""
echo "[LN-2024-002] Maria Garcia — Document Review"
ingest "LN-2024-002" "application" "$DATA/LN-2024-002/application.txt"
ingest "LN-2024-002" "appraisal"   "$DATA/LN-2024-002/appraisal.txt"

echo ""
echo "[LN-2024-003] Robert Johnson — Underwriting"
ingest "LN-2024-003" "application"          "$DATA/LN-2024-003/application.txt"
ingest "LN-2024-003" "credit_report"        "$DATA/LN-2024-003/credit_report.txt"
ingest "LN-2024-003" "income_verification"  "$DATA/LN-2024-003/income_verification.txt"
ingest "LN-2024-003" "tax_returns"          "$DATA/LN-2024-003/tax_returns.txt"

echo ""
echo "[LN-2024-004] Sarah Chen — Approved"
ingest "LN-2024-004" "application"          "$DATA/LN-2024-004/application.txt"
ingest "LN-2024-004" "appraisal"            "$DATA/LN-2024-004/appraisal.txt"
ingest "LN-2024-004" "underwriting_decision" "$DATA/LN-2024-004/underwriting_decision.txt"

echo ""
echo "[LN-2024-005] Michael Brown — Closing"
ingest "LN-2024-005" "application"          "$DATA/LN-2024-005/application.txt"
ingest "LN-2024-005" "closing_disclosure"   "$DATA/LN-2024-005/closing_disclosure.txt"
ingest "LN-2024-005" "title_insurance"      "$DATA/LN-2024-005/title_insurance.txt"
ingest "LN-2024-005" "final_approval"       "$DATA/LN-2024-005/final_approval.txt"

echo ""
echo "[POLICY] FHA Guidelines"
ingest "policy" "policy" "$DATA/FHA_policy_guidelines.txt"

echo ""
echo "Waiting 15s for worker to process all documents..."
sleep 15

echo ""
echo "Document status:"
for LOAN in LN-2024-001 LN-2024-002 LN-2024-003 LN-2024-004 LN-2024-005; do
  status_check "$LOAN"
done

echo ""
echo "================================"
echo " Demo data loaded!"
echo " UI:       http://localhost:5174"
echo " LangFuse: http://localhost:3002"
echo "================================"
