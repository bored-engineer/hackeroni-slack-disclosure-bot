package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/bored-engineer/hackeroni-ql/h1"
	slack "github.com/bored-engineer/slack-incoming-webhooks"
	"github.com/machinebox/graphql"
)

// The interval to refresh reports
const interval = 5 * time.Minute

// This is the query run once on bootstrap to get the security icon and most recent hacktivity item
var bootstrapQuery = `{
  team(handle: "security") {
    profile_picture(size: small)
  }
  hacktivity_items(
    secure_order_by: {
      field: latest_disclosable_activity_at, 
      direction: DESC
    }, 
    where: {
      report: {
        disclosed_at: {
          _is_null: false
        }
       }
      }, 
      first: 1
  ) {
    edges {
      node {
        ... on Disclosed {
          __typename
          report {
            disclosed_at
          }
        }
      }
    }
  }
}`

// This query gets all the info we need
var query = `query($since: DateTime) {
  hacktivity_items(
    secure_order_by: {
      field: latest_disclosable_activity_at, 
      direction: ASC
  	}, 
    where: {
      report: {
        disclosed_at: {
          _gt: $since
        }
      }
    }
  ) {
    edges {
      node {
        ... on Disclosed {
          __typename
          severity_rating
          report {
          	_id
            url
            title
            substate
            bounties {
              awarded_currency
              awarded_amount
            }
            disclosed_at
          }
          team {
            url
            name
          	profile_picture(size: large)
          }
          reporter {
            name
            username
            url
          	profile_picture(size: large)
          }
        }
      }
    }
  }
}`

// Entry Point
func main() {
	ctx := context.Background()

	// Setup the Slack client
	api := slack.Client{
		WebhookURL: os.Getenv("SLACK_WEBHOOK_URL"),
	}

	// Create a new HackerOne client
	client := graphql.NewClient(h1.GraphQLEndpoint)

	// Make the bootstrap request and parse the response
	bootstrapReq := graphql.NewRequest(bootstrapQuery)
	var bootstrapResp h1.Query
	if err := client.Run(ctx, bootstrapReq, &bootstrapResp); err != nil {
		log.Fatal(err)
	}

	// Extract the security icon
	// TODO: Technically this could change or expire
	securityIcon := *bootstrapResp.Team.ProfilePicture

	// Extract the most recent disclosure time
	disclosedSince := bootstrapResp.HacktivityItems.Edges[0].Node.Disclosed.Report.DisclosedAt.Add(time.Second)

	// Poll for new hacktivity every interval
	for range time.Tick(interval) {

		// Make the request with the "since" value from the last run/bootstrap
		req := graphql.NewRequest(query)
		req.Var("since", disclosedSince.String())
		// Run the query
		var resp h1.Query
		if err := client.Run(ctx, req, &resp); err != nil {
			log.Fatal(err)
		}

		// If we got no items, bail
		if resp.HacktivityItems == nil || resp.HacktivityItems.Edges == nil {
			continue
		}

		// If we got values, set disclosedAt to the last one (newest)
		if len(resp.HacktivityItems.Edges) > 0 {
			lastEdge := resp.HacktivityItems.Edges[len(resp.HacktivityItems.Edges)-1]
			if lastEdge.Node.Disclosed.Report == nil {
				continue
			}
			disclosedSince = lastEdge.Node.Disclosed.Report.DisclosedAt.Add(time.Second)
		}

		// For each report, post it
		for _, edge := range resp.HacktivityItems.Edges {
			pd := edge.Node.Disclosed

			// Convert the severity into a human readable value if possible
			var severity string
			if pd.SeverityRating != nil {
				switch *pd.SeverityRating {
				case h1.SeverityRatingEnumLow:
					severity = "Low"
				case h1.SeverityRatingEnumMedium:
					severity = "Medium"
				case h1.SeverityRatingEnumHigh:
					severity = "High"
				case h1.SeverityRatingEnumCritical:
					severity = "Critical"
				}
			}

			// Build the message attachment
			attachment := slack.Attachment{
				AuthorName: *pd.Reporter.Username,
				AuthorLink: pd.Reporter.URL.String(),
				AuthorIcon: *pd.Reporter.ProfilePicture,
				Title:      fmt.Sprintf("Report %s: %s", *pd.Report.ID_, *pd.Report.Title),
				TitleLink:  pd.Report.URL.String(),
				Footer:     "HackerOne Disclosure Bot",
				FooterIcon: securityIcon,
				MarkdownIn: []string{"text", "pretext"},
			}

			// Add the authors name if we have it
			if pd.Reporter.Name != nil && *pd.Reporter.Name != "" {
				attachment.AuthorName += fmt.Sprintf(" (%s)", *pd.Reporter.Name)
			}

			// TODO: Summaries

			// Set the attachment color based on the report state (extracted from CSS)
			switch *pd.Report.Substate {
			case string(h1.ReportStateEnumNew):
				attachment.Color = "#8e44ad"
			case string(h1.ReportStateEnumTriaged):
				attachment.Color = "#e67e22"
			case string(h1.ReportStateEnumResolved):
				attachment.Color = "#609828"
			case string(h1.ReportStateEnumNotApplicable):
				attachment.Color = "#ce3f4b"
			case string(h1.ReportStateEnumInformative):
				attachment.Color = "#ccc"
			case string(h1.ReportStateEnumDuplicate):
				attachment.Color = "#a78260"
			case string(h1.ReportStateEnumSpam):
				attachment.Color = "#555"
			}

			// If the report has a bounty, add it
			if len(pd.Report.Bounties) > 0 {
				// TODO: This isn't great if there are multiple bounties
				bounty := pd.Report.Bounties[0]
				formattedBounty := *bounty.AwardedAmount + " " + *bounty.AwardedCurrency
				attachment.Fallback = formattedBounty + " - "
				attachment.AddField(&slack.Field{
					Title: "Bounty",
					Value: formattedBounty,
					Short: true,
				})
			}

			// If the report has a severity, add it
			if severity != "" {
				attachment.Fallback += severity + " - "
				attachment.AddField(&slack.Field{
					Title: "Severity",
					Value: severity,
					Short: true,
				})
			}

			// Finally append the report title and URL to the fallback
			attachment.Fallback += "\"" + *pd.Report.Title + "\""
			attachment.Fallback += " - " + pd.Report.URL.String()

			// If we have the exact time it was disclosed add that
			if pd.Report.DisclosedAt != nil {
				attachment.Timestamp = pd.Report.DisclosedAt.Unix()
			}

			// Post the actual message
			log.Printf("Posting: %v", attachment)
			err := api.Post(&slack.Payload{
				Username:    *pd.Team.Name + " Disclosed",
				IconURL:     *pd.Team.ProfilePicture,
				Attachments: []*slack.Attachment{&attachment},
			})
			if err != nil {
				log.Printf("api.Post failed: %v", err)
			}

		}

	}
}
