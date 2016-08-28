# hackeroni-slack-disclosure-bot
A [Slack](https://slack.com) bot that posts a message everytime a [HackerOne](https://hackerone.com) report is publicly disclosed. The messages look like this:

![message](message.png?raw=true "Message")

## Installation
The bot relies on [uber-go/hackeroni](https://github.com/uber-go/hackeroni) for HackerOne integration (`legacy` package) and [monochromegane/slack-incoming-webhooks](https://github.com/monochromegane/slack-incoming-webhooks) for Slack integration.

These packages can be installed via [glide](https://glide.sh) using the following commands:
```shell
glide update
go build
```

## Setup
The bot uses Slack's [Incoming WebHooks](https://api.slack.com/incoming-webhooks) and POSTs messages to the URL specified by the `SLACK_WEBHOOK_URL` environment variable. Simply create a Incoming WebHook and add the URL to the environment.