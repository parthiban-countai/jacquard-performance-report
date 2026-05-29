import json
import boto3
from botocore.exceptions import ClientError


REGION_NAME = "ap-south-1"
DB_SECRET_NAME  = "KNITI_CENTRAL_DB"


def _fetch_secret(secret_name: str, secret_key: str) -> str:
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=REGION_NAME)
    try:
        response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise RuntimeError(f"Failed to fetch secret '{secret_name}' from AWS Secrets Manager: {e}") from e
    raw = response["SecretString"]
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if isinstance(parsed, dict):
        return parsed.get(secret_key) or next(iter(parsed.values()))
    return raw


def get_db_secrets(secret_key) -> str:
    return _fetch_secret(DB_SECRET_NAME, secret_key)