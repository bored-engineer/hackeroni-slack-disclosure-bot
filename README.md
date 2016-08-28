# hackeroni-slack-disclosure-bot
This is a [Slack](https://slack.com) bot the posts whenever a [HackerOne](https://hackerone.com) report is publicly disclosed. The messages look like this:

![message](message.png?raw=true "Title")

## Installation
The bot uses Slack's [Incoming WebHooks](https://api.slack.com/incoming-webhooks) and POSTs messages to the URL specified by the `SLACK_WEBHOOK_URL` environment variable.
It relies on [uber-go/hackeroni](https://github.com/uber-go/hackeroni) for HackerOne integration (`legacy` package) and [monochromegane/slack-incoming-webhooks](https://github.com/monochromegane/slack-incoming-webhooks) for Slack integration.