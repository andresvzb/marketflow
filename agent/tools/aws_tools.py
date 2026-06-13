"""
AWS tools — Claude calls these to provision real infrastructure.

Each entry in AWS_TOOLS is the JSON schema Claude sees. The matching
dispatch_aws_tool() function runs the real boto3 code locally.
"""

import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Tool definitions (what Claude sees)
# ---------------------------------------------------------------------------

AWS_TOOLS = [
    {
        "name": "create_s3_bucket",
        "description": (
            "Create an S3 bucket for a specific medallion layer (bronze, silver, gold). "
            "The bucket name is auto-prefixed with the project name and environment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["bronze", "silver", "gold"],
                    "description": "Medallion layer this bucket belongs to.",
                },
                "region": {
                    "type": "string",
                    "description": "AWS region (default: us-east-1).",
                    "default": "us-east-1",
                },
            },
            "required": ["layer"],
        },
    },
    {
        "name": "create_glue_database",
        "description": "Create an AWS Glue Data Catalog database for a medallion layer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["bronze", "silver", "gold"],
                    "description": "Medallion layer.",
                },
            },
            "required": ["layer"],
        },
    },
    {
        "name": "list_s3_buckets",
        "description": "List all S3 buckets in the account that belong to this project.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _bucket_name(layer: str) -> str:
    prefix = os.getenv("S3_BUCKET_PREFIX", "marketflow")
    env = os.getenv("ENVIRONMENT", "dev")
    return f"{prefix}-{layer}-{env}"


def _create_s3_bucket(layer: str, region: str = "us-east-1") -> str:
    name = _bucket_name(layer)
    s3 = boto3.client("s3", region_name=region)
    try:
        if region == "us-east-1":
            s3.create_bucket(Bucket=name)
        else:
            s3.create_bucket(
                Bucket=name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        # Block all public access
        s3.put_public_access_block(
            Bucket=name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        return f"Created bucket: {name} (region={region}, public access blocked)"
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            return f"Bucket already exists: {name}"
        raise


def _create_glue_database(layer: str) -> str:
    project = os.getenv("PROJECT_NAME", "marketflow")
    env = os.getenv("ENVIRONMENT", "dev")
    db_name = f"{project}_{layer}_{env}"
    glue = boto3.client("glue")
    try:
        glue.create_database(
            DatabaseInput={
                "Name": db_name,
                "Description": f"MarketFlow {layer} layer — {env}",
            }
        )
        return f"Created Glue database: {db_name}"
    except ClientError as e:
        if e.response["Error"]["Code"] == "AlreadyExistsException":
            return f"Glue database already exists: {db_name}"
        raise


def _list_s3_buckets() -> str:
    prefix = os.getenv("S3_BUCKET_PREFIX", "marketflow")
    s3 = boto3.client("s3")
    response = s3.list_buckets()
    project_buckets = [
        b["Name"] for b in response.get("Buckets", []) if b["Name"].startswith(prefix)
    ]
    if not project_buckets:
        return "No project buckets found."
    return "Project buckets:\n" + "\n".join(f"  - {b}" for b in project_buckets)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch_aws_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "create_s3_bucket":
        return _create_s3_bucket(**args)
    if name == "create_glue_database":
        return _create_glue_database(**args)
    if name == "list_s3_buckets":
        return _list_s3_buckets()
    return f"Unknown AWS tool: {name}"
