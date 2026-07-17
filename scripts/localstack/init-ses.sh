#!/bin/bash
# LocalStack SES/SNS initialization.
# Verifies the sender identity and creates an SNS topic so the full
# send -> event pipeline can be exercised locally.
set -e

echo "Waiting for LocalStack SES to be ready..."
until awslocal ses list-identities 2>/dev/null; do
  echo "SES not ready yet, waiting..."
  sleep 1
done

FROM_ADDR="${SES_FROM_ADDRESS:-campaigns@controlhub.local}"

echo "Verifying SES identity (v1): $FROM_ADDR"
awslocal ses verify-email-identity --email-address "$FROM_ADDR" 2>/dev/null || echo "identity verify skipped"

# Also verify the domain so any from-address on it works in dev.
DOMAIN="${FROM_ADDR#*@}"
echo "Verifying SES domain identity: $DOMAIN"
awslocal ses verify-domain-identity --domain "$DOMAIN" 2>/dev/null || echo "domain verify skipped"

echo "Creating SNS topic: controlhub-ses-events"
awslocal sns create-topic --name controlhub-ses-events 2>/dev/null || echo "topic exists"

echo "SES/SNS init complete. Verified identities:"
awslocal ses list-identities || true
