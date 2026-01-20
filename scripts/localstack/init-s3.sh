#!/bin/bash
# LocalStack S3 initialization script
# Creates the uploads bucket on LocalStack startup

set -e

echo "Waiting for LocalStack S3 to be ready..."
until awslocal s3 ls 2>/dev/null; do
  echo "S3 not ready yet, waiting..."
  sleep 1
done

BUCKET_NAME="${S3_BUCKET_NAME:-controlhub-uploads}"

echo "Creating S3 bucket: $BUCKET_NAME"
awslocal s3 mb "s3://$BUCKET_NAME" 2>/dev/null || echo "Bucket already exists"

echo "Setting bucket CORS configuration..."
awslocal s3api put-bucket-cors --bucket "$BUCKET_NAME" --cors-configuration '{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
      "AllowedOrigins": ["http://localhost:3001", "http://localhost:9000"],
      "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
      "MaxAgeSeconds": 3600
    }
  ]
}'

echo "Bucket $BUCKET_NAME created and configured successfully!"
awslocal s3 ls
