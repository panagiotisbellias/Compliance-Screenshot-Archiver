#!/usr/bin/env python3
"""
Setup script to create DynamoDB tables for local development.
"""

import boto3
import sys
from botocore.exceptions import ClientError


def create_schedules_table(dynamodb, table_name="schedules"):
    """Create the schedules table."""
    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "schedule_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "schedule_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "next_capture_time", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserSchedulesIndex",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "next_capture_time", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
                {
                    "IndexName": "NextCaptureIndex",
                    "KeySchema": [{"AttributeName": "next_capture_time", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
            ],
            BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Wait until the table exists
        table.meta.client.get_waiter("table_exists").wait(TableName=table_name)
        print(f"Created table: {table_name}")
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table {table_name} already exists")
            return True
        else:
            print(f"Error creating table {table_name}: {e}")
            return False


def create_captures_table(dynamodb, table_name="captures"):
    """Create the captures table."""
    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "capture_id", "KeyType": "HASH"},
                {"AttributeName": "created_at", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "capture_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "N"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "url", "AttributeType": "S"},
                {"AttributeName": "sha256", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UserCapturesIndex",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
                {
                    "IndexName": "UrlCapturesIndex",
                    "KeySchema": [
                        {"AttributeName": "url", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
                {
                    "IndexName": "HashIndex",
                    "KeySchema": [{"AttributeName": "sha256", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                    "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
                },
            ],
            BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        # Wait until the table exists
        table.meta.client.get_waiter("table_exists").wait(TableName=table_name)
        print(f"Created table: {table_name}")
        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table {table_name} already exists")
            return True
        else:
            print(f"Error creating table {table_name}: {e}")
            return False


def main():
    """Main setup function."""
    print("Setting up DynamoDB tables for Compliance Screenshot Archiver...")

    # Create DynamoDB resource
    try:
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        print("Connected to DynamoDB")
    except Exception as e:
        print(f"Failed to connect to DynamoDB: {e}")
        print("Make sure you have AWS credentials configured (aws configure)")
        sys.exit(1)

    # Create tables
    success = True
    success &= create_schedules_table(dynamodb)
    success &= create_captures_table(dynamodb)

    if success:
        print("All tables created successfully!")
        print("\nNext steps:")
        print("1. Your backend should now be able to store real captures")
        print("2. Create some captures using the frontend")
        print("3. They should appear in the archive page")
    else:
        print("Some tables failed to create")
        sys.exit(1)


if __name__ == "__main__":
    main()
