import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

import boto3
import requests
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from bs4 import BeautifulSoup

sqs = boto3.client("sqs")
tracer = Tracer()


@tracer.capture_method
def refresh_csrf(session: requests.Session):
    """Refresh the CSRF token for the session by requesting a webpage."""
    response = session.get("https://hackerone.com/hacktivity")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, features="html.parser")
    csrf_token = soup.select_one('meta[name="csrf-token"]')["content"]
    session.headers["x-csrf-token"] = csrf_token


@tracer.capture_method
def fetch_hacktivity(session: requests.Session, since: datetime) -> List[Any]:
    """Scrape the hacktivity since a given datetime."""
    response = session.post(
        "https://hackerone.com/graphql",
        json={
            "query": (Path(__file__).parent / "query.graphql").read_text(),
            "variables": {
                "since": since.isoformat(),
            },
        },
    )
    response.raise_for_status()
    print(f"response: {response.text}")
    return response.json()["data"]["hacktivity_items"]["nodes"]


@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext):
    """Entrypoint when invoked by Lambda schedule."""
    with requests.Session() as session:
        # This CSRF check is new as of Auguest 2022 and rather annoying
        refresh_csrf(session)
        # Lookback 4 minutes (SNS de-duplication window is 5 minutes)
        since = datetime.utcnow() - timedelta(minutes=4)
        # Fetch all events since that time (already sorted)
        for event in fetch_hacktivity(session, since):
            # Submit to SQS using a de-duplication ID
            sqs.send_message(
                QueueUrl=os.environ["SQS_QUEUE"],
                MessageBody=json.dumps(event),
                MessageDeduplicationId=event.get("report", {}).get("_id"),
                MessageGroupId="hacktivity",
            )


if __name__ == "__main__":
    lambda_handler({}, None)
