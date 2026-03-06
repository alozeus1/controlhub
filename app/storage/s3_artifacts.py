"""S3 artifact storage with security controls for Agent outputs."""

import json
import os
from datetime import datetime

from botocore.exceptions import ClientError

from app.storage.s3 import build_s3_client


def get_artifact_storage_config():
    environment = os.environ.get("ENVIRONMENT", "development")
    bucket_prefix = os.environ.get("ARTIFACTS_BUCKET_PREFIX", "controlhub-artifacts")
    bucket = f"{bucket_prefix}-{environment}".lower()

    return {
        "bucket": bucket,
        "region": os.environ.get("AWS_REGION", "us-east-1"),
        "kms_key_arn": os.environ.get("ARTIFACTS_KMS_KEY_ARN"),
    }


def _secure_bucket_policy(bucket_name):
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DenyInsecureTransport",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [f"arn:aws:s3:::{bucket_name}", f"arn:aws:s3:::{bucket_name}/*"],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
            {
                "Sid": "DenyUnEncryptedObjectUploads",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
                "Condition": {
                    "StringNotEquals": {
                        "s3:x-amz-server-side-encryption": "aws:kms",
                    }
                },
            },
        ],
    }


def ensure_artifact_bucket():
    config = get_artifact_storage_config()
    client = build_s3_client()

    bucket = config["bucket"]
    region = config["region"]
    kms_key_arn = config["kms_key_arn"]

    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        create_args = {"Bucket": bucket}
        if region != "us-east-1":
            create_args["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**create_args)

    client.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )

    encryption_rule = {
        "ApplyServerSideEncryptionByDefault": {
            "SSEAlgorithm": "aws:kms",
        },
        "BucketKeyEnabled": True,
    }
    if kms_key_arn:
        encryption_rule["ApplyServerSideEncryptionByDefault"]["KMSMasterKeyID"] = kms_key_arn

    client.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [encryption_rule],
        },
    )

    client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(_secure_bucket_policy(bucket)))

    return bucket


def put_artifact_object(s3_key, payload_bytes, mime_type):
    bucket = ensure_artifact_bucket()
    client = build_s3_client()

    put_args = {
        "Bucket": bucket,
        "Key": s3_key,
        "Body": payload_bytes,
        "ContentType": mime_type,
        "ServerSideEncryption": "aws:kms",
        "Metadata": {
            "uploaded-at": datetime.utcnow().isoformat(),
        },
    }
    kms_key_arn = os.environ.get("ARTIFACTS_KMS_KEY_ARN")
    if kms_key_arn:
        put_args["SSEKMSKeyId"] = kms_key_arn

    client.put_object(**put_args)
    return bucket


def read_artifact_object(s3_bucket, s3_key):
    client = build_s3_client()
    response = client.get_object(Bucket=s3_bucket, Key=s3_key)
    return response["Body"].read()


def generate_artifact_presigned_url(s3_bucket, s3_key, download_filename, expires_seconds):
    client = build_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": s3_bucket,
            "Key": s3_key,
            "ResponseContentDisposition": f'attachment; filename="{download_filename}"',
        },
        ExpiresIn=expires_seconds,
    )
