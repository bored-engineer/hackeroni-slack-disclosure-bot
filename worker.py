import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

session = requests.Session()
session.headers["User-Agent"] = "github.com/bored-engineer/hackeroni-slack-disclosure-bot"

# TODO: Don't hard-code this URL, fetch at launch?
LOGO_URL = "https://profile-photos.hackerone-user-content.com/variants/000/000/013/fa942b9b1cbf4faf37482bf68458e1195aab9c02_original.png/0621f211aae8984f02f017decf83d0064fe91a6a16b11f840ecf5b53ddb7b872"


def refresh_csrf():
    """Refresh the CSRF token for the session by requesting a webpage and parsing it."""
    response = session.get("https://hackerone.com/hacktivity")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, features="html.parser")
    csrf_token = soup.select_one('meta[name="csrf-token"]')["content"]
    session.headers["x-csrf-token"] = csrf_token


def fetch_hacktivity(since: datetime) -> List[Any]:
    """Scrape the hacktivity since a given datetime."""
    # Make a POST using query.graphql
    response = session.post(
        "https://hackerone.com/graphql",
        json={
            "query": (Path(__file__).parent / "query.graphql").read_text(),
            "variables": {
                "since": since.isoformat(),
            },
        },
    )
    # If there's still an error, raise it and give up
    response.raise_for_status()
    # Filter the results to only the "Disclosed" objects, ignore everything else
    nodes = response.json()["data"]["hacktivity_items"]["nodes"]
    nodes = filter(lambda node: node["__typename"] == "Disclosed", nodes)
    return list(nodes)


def post_slack(payload: dict):
    # All reporters have a username, some have an actual name as well
    reporter_name = payload["reporter"]["username"]
    if payload["reporter"]["name"]:
        reporter_name = payload["reporter"]["name"] + f" ({reporter_name})"

    # The reporter profile picture may not be a fully qualified URL
    reporter_picture = payload["reporter"]["profile_picture"]
    if not reporter_picture.startswith("http"):
        reporter_picture = "https://hackerone.com" + reporter_picture

    # Build up the attachment from the fields
    attachment = {
        "author_name": reporter_name,
        "author_link": payload["reporter"]["url"],
        "author_icon": reporter_picture,
        "title": f'Report {payload["report"]["_id"]}: {payload["report"]["title"]}',
        "title_link": payload["report"]["url"],
        "footer": "HackerOne Disclosure Bot",
        "footer_icon": LOGO_URL,
        "mrkdwn_in": ["text", "pretext"],
        "fields": [],
        "fallback": f'"{payload["report"]["title"]}" - {payload["report"]["url"]}',
    }

    # If there was a severity, add that as a field and set the color
    if payload["severity_rating"]:
        severity = payload["severity_rating"].replace("_", " ").title()
        attachment["fallback"] += f" - {severity}"
        attachment["fields"].append(
            {
                "title": "Severity",
                "value": severity,
                "short": True,
            }
        )
        # Extracted from the H1 UI to match
        if severity == "New":
            attachment["color"] = "#8e44ad"
        elif severity == "Triaged":
            attachment["color"] = "#e67e22"
        elif severity == "Resolved":
            attachment["color"] = "#609828"
        elif severity == "Not Applicable":
            attachment["color"] = "#ce3f4b"
        elif severity == "Informative":
            attachment["color"] = "#ccc"
        elif severity == "Duplicate":
            attachment["color"] = "#a78260"
        elif severity == "Spam":
            attachment["color"] = "#555"

    # If there was a rewarded amount, add that as a field
    if payload["total_awarded_amount"]:
        amount = f'{payload["total_awarded_amount"]} {payload["currency"]}'
        attachment["fallback"] += f" - {amount}"
        attachment["fields"].append(
            {
                "title": "Bounty",
                "value": amount,
                "short": True,
            }
        )

    # Match the timestamp in Slack to the actual disclosure date
    if payload["report"]["disclosed_at"]:
        disclosed_at_iso = payload["report"]["disclosed_at"].rstrip("Z")
        disclosed_at_unix = datetime.fromisoformat(disclosed_at_iso).timestamp()
        attachment["timestamp"] = disclosed_at_unix

    # The team profile picture may not be a fully qualified URL
    team_picture = payload["team"]["profile_picture"]
    if not team_picture.startswith("http"):
        team_picture = "https://hackerone.com" + team_picture

    # Fire the attachment off to slack as a payload
    response = requests.post(
        url=os.environ["SLACK_WEBHOOK_URL"],
        json={
            "username": f'{payload["team"]["name"]} disclosed',
            "icon_url": team_picture,
            "attachments": [attachment],
        },
    )
    response.raise_for_status()


def main():
    """worker entrypoint."""
    # This is just going to grow unconditionally, oh well
    seen = set()
    # Loop forever until we get SIGINT (KeyboardInterrupt)
    while True:
        try:
            # Fetch all hacktivity from the last 15 minutes
            since = datetime.utcnow() - timedelta(minutes=15)
            try:
                events = fetch_hacktivity(since)
            except requests.exceptions.HTTPError as e:
                # If it fails with 'STANDARD_ERROR' it's a CSRF token issue, refresh it and try again
                if e.response.status_code != 500 or '"STANDARD_ERROR"' not in e.response.text:
                    raise
                logging.info(f"CSRF token invalid, refreshing...")
                refresh_csrf()
                events = fetch_hacktivity(since)
            # For each of the hacktivity events, send to Slack
            for event in events:
                # Make sure we don't post the same report multiple times
                report_id = event["report"]["_id"]
                if report_id in seen:
                    logging.info(f"Ignoring {report_id} as it was already seen...")
                    continue
                seen.add(report_id)
                # Post the event to Slack
                logging.info(f"Posting {report_id} to Slack...")
                post_slack(event)
        except KeyboardInterrupt:
            break
        except:
            logging.exception("execution failed")
        # Poll at most every minute
        time.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
