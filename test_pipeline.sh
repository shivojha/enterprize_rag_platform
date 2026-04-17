#!/bin/bash
# Test the full Mortgage RAG pipeline end-to-end
set -e

API="http://localhost:8002"
LOAN_ID="LN-2024-001"

echo "================================"
echo " Mortgage RAG POC - E2E Test"
echo "================================"

# 1. Health check
echo ""
echo "[1] Health check..."
curl -s "$API/health" | python3 -m json.tool

# 2. Ingest loan application
echo ""
echo "[2] Ingesting loan application..."
curl -s -X POST "$API/ingest/$LOAN_ID?doc_type=application" \
  -F "file=@data/sample_loans/LN-2024-001_application.txt" | python3 -m json.tool

# 3. Ingest FHA policy guidelines
echo ""
echo "[3] Ingesting FHA policy guidelines..."
curl -s -X POST "$API/ingest/policy?doc_type=policy" \
  -F "file=@data/sample_loans/FHA_policy_guidelines.txt" | python3 -m json.tool

echo ""
echo "[4] Waiting 10s for worker to process..."
sleep 10

# 4. Check loan status
echo ""
echo "[5] Loan document status..."
curl -s "$API/loans/$LOAN_ID/status" | python3 -m json.tool

# 5. Query - eligibility check
echo ""
echo "[6] Query: Is John Smith eligible for FHA loan?"
curl -s -X POST "$API/query" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Is borrower John Smith eligible for an FHA loan? Check DTI, credit score, and down payment.\", \"loan_id\": \"$LOAN_ID\"}" \
  | python3 -m json.tool

# 6. Query - missing documents
echo ""
echo "[7] Query: What documents are missing?"
curl -s -X POST "$API/query" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What documents are missing for loan LN-2024-001 to proceed to underwriting?\", \"loan_id\": \"$LOAN_ID\"}" \
  | python3 -m json.tool

# 7. Query - MIP calculation
echo ""
echo "[8] Query: Calculate MIP cost"
curl -s -X POST "$API/query" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What is the upfront MIP amount for this loan?\", \"loan_id\": \"$LOAN_ID\"}" \
  | python3 -m json.tool

echo ""
echo "================================"
echo " Test complete!"
echo " API docs: http://localhost:8001/docs"
echo "================================"
