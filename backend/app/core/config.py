from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class Settings(BaseModel):
    """
    Centralized settings loaded from env (dotenv in dev; Secrets/SSM in prod).
    """

    env: str = Field(default=os.getenv("APP_ENV", "dev"))
    aws_region: str = Field(default=os.getenv("AWS_REGION", "us-east-1"))

    # API
    api_base_path: str = Field(default=os.getenv("API_BASE_PATH", "/api"))

    # Cognito Configuration
    cognito_user_pool_id: str | None = os.getenv("COGNITO_USER_POOL_ID")
    cognito_client_id: str | None = os.getenv("COGNITO_CLIENT_ID")
    cognito_region: str = Field(default=os.getenv("COGNITO_REGION", "us-east-1"))
    jwt_audience: str | None = os.getenv("JWT_AUDIENCE")
    jwt_issuer: str | None = os.getenv("JWT_ISSUER")
    jwt_jwks_url: AnyHttpUrl | None = Field(default=None)  # Cognito JWKS

    # Data
    s3_bucket_artifacts: str = Field(default=os.getenv("S3_BUCKET_ARTIFACTS", ""))
    kms_key_arn: str | None = os.getenv("KMS_KEY_ARN")
    ddb_table_schedules: str = Field(default=os.getenv("DDB_TABLE_SCHEDULES", "schedules"))
    ddb_table_captures: str = Field(default=os.getenv("DDB_TABLE_CAPTURES", "captures"))

    # Security
    presign_ttl_seconds: int = Field(default=int(os.getenv("PRESIGN_TTL_SECONDS", "300")))

    @field_validator("jwt_jwks_url", mode="before")
    @classmethod
    def parse_jwks_url(cls, v):
        # If no value provided, get from environment or construct from Cognito settings
        if v is None:
            v = os.getenv("JWT_JWKS_URL")
            # If still None, try to construct from Cognito settings
            if v is None:
                cognito_region = os.getenv("COGNITO_REGION", "us-east-1")
                cognito_user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
                if cognito_user_pool_id:
                    v = f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}/.well-known/jwks.json"
        # Return None if still empty
        if v is None or v == "":
            return None
        # Convert string to AnyHttpUrl
        return AnyHttpUrl(v)


def load_env() -> Settings:
    """
    Load environment variables (dotenv in dev) and return typed Settings.

    Returns:
        Settings: Parsed, validated settings.
    """
    # Reason: local dev convenience; prod should inject env via platform.
    if os.getenv("APP_ENV", "dev") == "dev":
        load_dotenv()
    return Settings()


settings = load_env()
