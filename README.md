# Hackeroni Slack Public Disclosure Bot
A [Slack](https://slack.com) bot that posts a message everytime a [HackerOne](https://hackerone.com) report is publicly disclosed. The messages look like this:

![message](https://cloud.githubusercontent.com/assets/541842/21532083/789e86e0-cd12-11e6-9b20-21a9114b99cc.png)

## Installation
The bot relies on [bored-engineer/hackeroni-ql](https://github.com/bored-engineer/hackeroni-ql) for HackerOne integration via GraphQL and [monochromegane/slack-incoming-webhooks](https://github.com/monochromegane/slack-incoming-webhooks) for Slack integration.

The bot can be built using the following command:
```shell
go build
```

## Setup
The bot uses Slack's [Incoming WebHooks](https://api.slack.com/incoming-webhooks) and POSTs messages to the URL specified by the `SLACK_WEBHOOK_URL` environment variable. Simply create a Incoming WebHook and add the URL to the environment.
