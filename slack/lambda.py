import json
import os
from datetime import datetime

import requests
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    batch_processor,
)
from aws_lambda_powertools.utilities.data_classes.sqs_event import SQSRecord
from aws_lambda_powertools.utilities.typing import LambdaContext

processor = BatchProcessor(event_type=EventType.SQS)
tracer = Tracer()


@tracer.capture_method
def record_handler(record: SQSRecord):
    # (re)parse the incoming request body
    payload = json.loads(record.body)

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
        "footer_icon": "https://profile-photos.hackerone-user-content.com/variants/000/000/013/fa942b9b1cbf4faf37482bf68458e1195aab9c02_original.png/0621f211aae8984f02f017decf83d0064fe91a6a16b11f840ecf5b53ddb7b872",
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


@tracer.capture_lambda_handler
@batch_processor(record_handler=record_handler, processor=processor)
def lambda_handler(event, context: LambdaContext):
    return processor.response()


if __name__ == "__main__":
    record_handler(
        SQSRecord(
            data={
                "body": json.dumps(
                    {
                        "id": "12345",
                        "severity_rating": "critical",
                        "currency": "USD",
                        "total_awarded_amount": "1337",
                        "report": {
                            "_id": "1337",
                            "url": "https://hackerone.com/bored-engineer",
                            "title": "Testing Report",
                            "substate": "resolved",
                            "disclosed_at": "2022-09-04T13:23:03.840Z",
                        },
                        "team": {
                            "url": "https://hackerone.com/bored-engineer",
                            "name": "bored-engineer",
                            "profile_picture": "https://hackerone-us-west-2-production-attachments.s3.us-west-2.amazonaws.com/variants/xh0k94drzpd2d2z4bz9b1kbzngbh/85262aa80c1b0a9084532ae18b3d746a50817aadbb3dff7c8290425c702034b1?response-content-disposition=inline%3B%20filename%3D%22IMG_0330%20%25281%2529.jpg%22%3B%20filename%2A%3DUTF-8%27%27IMG_0330%2520%25281%2529.jpg&response-content-type=image%2Fjpeg&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=ASIAQGK6FURQVVODYHT5%2F20220906%2Fus-west-2%2Fs3%2Faws4_request&X-Amz-Date=20220906T001307Z&X-Amz-Expires=3600&X-Amz-Security-Token=IQoJb3JpZ2luX2VjEFcaCXVzLXdlc3QtMiJHMEUCIQD%2F0LGz5Dblzw2v7mb5zwAiuNWJ1lcAbAaUcDSX3vyLIgIgSY2LEkJQ5dLS9AL7zUbfl8uhnwuxhf9gr5fPEX8g6kIq1QQI4P%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARADGgwwMTM2MTkyNzQ4NDkiDC%2Bb%2B5saQ6KrmtoUtyqpBKk3KcvzNd77KXPK7unHz3UGjW2XCX3ALP%2FqZMP3%2FF4jCHeer3fI6LevXVv9Zjjpa%2ByxdH0TKuJHlFBiGm7F33yadrvMfGsZG9s0QiDoQ4%2FXjMY0bhCffE%2BC6X2fkkY38pGq%2BLEJ7yNpaCk13e%2FwzSap4cCAo7PtEsySqSbNChmMxEjHZoAKr6vNDFXqZrXyaShkQiPyWCAVrJMR6ezJ0HopovbYi3dxxFrYh1vm9l1395JmPjHw9XCPMGLztoA4lz2VA9Dq0XmiOeFx0DK28gTDkzQfE6coaSJiv3z5lGffq2TiCv5qIg1MPMt9yN1Rwcc7YgomJWX1y9web%2FcussSsFSF%2FFqwUziuewGNJFfopgF1tN5LpVGqguBD%2F0wbO1o2%2BTnICNQbjlRa6OJFCIKRWj7uubw1SGF1oWLfeYMAeilJ5Hr0mFwO6IeGuw81ZRys6t0vCV%2Fw4Lrjn0HWRTEHmKPkdK8mAi%2Fy0KispRU3tPxfGCcM%2FmjU5HdBEqoPmpDUvO74Z6FhZstwtyBulHwkxuPiDbDYPGxtSH8p3%2B8u5temGaj6epYlkM8xIkBnyEfS21pZIqkAtl%2FT5yZQA5GIaiwur%2FcQpE5duj9WRCslhOP%2Bad3GtK6VHuIRpIUmHwKSAYgzvapHoXmiHcYxrFcjpRVJ3WJ4UrRRQ7sapt0WL3Axb%2B%2FsdfLymQypXOY6v1nBNzhhDBB%2BboPgNvC7p4kvBu5nv7oWXR2IwhPzZmAY6qQHKci904iV%2F06%2FuVa4y29BrxDvfv7bcM3y16Rqpf1zkNui%2BYyL9Vh5bw4XtO4HSMHdkhX9HhpyAJNooHR%2Fs%2B7kNAe8Z2EeRdMNSkKxe3YdypUJQfK5KPNO7E1d9UzC8mVoNT%2F0hwdB3pNtHYWk7RQg8EryB7IhbLttpEmp9jfMTY1BZ0wIubKxoeWw249Bf1cZkd0hdjjhHQZvQ82CxBIuG7tOHs4l%2BxPPy&X-Amz-SignedHeaders=host&X-Amz-Signature=00864d995539bb72fb0e676619b67dd0b6639c82174c812f4b72fb6467ac8c63",
                        },
                        "reporter": {
                            "name": "Luke Young",
                            "username": "bored-engineer",
                            "url": "https://hackerone.com/bored-engineer",
                            "profile_picture": "https://hackerone-us-west-2-production-attachments.s3.us-west-2.amazonaws.com/variants/xh0k94drzpd2d2z4bz9b1kbzngbh/85262aa80c1b0a9084532ae18b3d746a50817aadbb3dff7c8290425c702034b1?response-content-disposition=inline%3B%20filename%3D%22IMG_0330%20%25281%2529.jpg%22%3B%20filename%2A%3DUTF-8%27%27IMG_0330%2520%25281%2529.jpg&response-content-type=image%2Fjpeg&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=ASIAQGK6FURQVVODYHT5%2F20220906%2Fus-west-2%2Fs3%2Faws4_request&X-Amz-Date=20220906T001307Z&X-Amz-Expires=3600&X-Amz-Security-Token=IQoJb3JpZ2luX2VjEFcaCXVzLXdlc3QtMiJHMEUCIQD%2F0LGz5Dblzw2v7mb5zwAiuNWJ1lcAbAaUcDSX3vyLIgIgSY2LEkJQ5dLS9AL7zUbfl8uhnwuxhf9gr5fPEX8g6kIq1QQI4P%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FARADGgwwMTM2MTkyNzQ4NDkiDC%2Bb%2B5saQ6KrmtoUtyqpBKk3KcvzNd77KXPK7unHz3UGjW2XCX3ALP%2FqZMP3%2FF4jCHeer3fI6LevXVv9Zjjpa%2ByxdH0TKuJHlFBiGm7F33yadrvMfGsZG9s0QiDoQ4%2FXjMY0bhCffE%2BC6X2fkkY38pGq%2BLEJ7yNpaCk13e%2FwzSap4cCAo7PtEsySqSbNChmMxEjHZoAKr6vNDFXqZrXyaShkQiPyWCAVrJMR6ezJ0HopovbYi3dxxFrYh1vm9l1395JmPjHw9XCPMGLztoA4lz2VA9Dq0XmiOeFx0DK28gTDkzQfE6coaSJiv3z5lGffq2TiCv5qIg1MPMt9yN1Rwcc7YgomJWX1y9web%2FcussSsFSF%2FFqwUziuewGNJFfopgF1tN5LpVGqguBD%2F0wbO1o2%2BTnICNQbjlRa6OJFCIKRWj7uubw1SGF1oWLfeYMAeilJ5Hr0mFwO6IeGuw81ZRys6t0vCV%2Fw4Lrjn0HWRTEHmKPkdK8mAi%2Fy0KispRU3tPxfGCcM%2FmjU5HdBEqoPmpDUvO74Z6FhZstwtyBulHwkxuPiDbDYPGxtSH8p3%2B8u5temGaj6epYlkM8xIkBnyEfS21pZIqkAtl%2FT5yZQA5GIaiwur%2FcQpE5duj9WRCslhOP%2Bad3GtK6VHuIRpIUmHwKSAYgzvapHoXmiHcYxrFcjpRVJ3WJ4UrRRQ7sapt0WL3Axb%2B%2FsdfLymQypXOY6v1nBNzhhDBB%2BboPgNvC7p4kvBu5nv7oWXR2IwhPzZmAY6qQHKci904iV%2F06%2FuVa4y29BrxDvfv7bcM3y16Rqpf1zkNui%2BYyL9Vh5bw4XtO4HSMHdkhX9HhpyAJNooHR%2Fs%2B7kNAe8Z2EeRdMNSkKxe3YdypUJQfK5KPNO7E1d9UzC8mVoNT%2F0hwdB3pNtHYWk7RQg8EryB7IhbLttpEmp9jfMTY1BZ0wIubKxoeWw249Bf1cZkd0hdjjhHQZvQ82CxBIuG7tOHs4l%2BxPPy&X-Amz-SignedHeaders=host&X-Amz-Signature=00864d995539bb72fb0e676619b67dd0b6639c82174c812f4b72fb6467ac8c63",
                        },
                    }
                )
            }
        )
    )
