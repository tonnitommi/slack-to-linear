import os
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

slack_token = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=slack_token)

@app.route("/slack/command", methods=["POST"])
def handle_command():
    trigger_id = request.form.get("trigger_id")

    # Open a modal when the slash command is used
    try:
        response = slack_client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "issue_report_modal",
                "title": {
                    "type": "plain_text",
                    "text": "Report Issue"
                },
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "title_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Issue Title"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "title",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Enter the issue title"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Issue Description"
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "description",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Enter a detailed description"
                            }
                        }
                    },
                    {
                        "type": "input",
                        "block_id": "component_block",
                        "label": {
                            "type": "plain_text",
                            "text": "Component"
                        },
                        "element": {
                            "type": "static_select",
                            "action_id": "component",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Select a component"
                            },
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "ACE"
                                    },
                                    "value": "cbef7a2c-1a77-4a5c-b214-39188924d63f"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Control Room"
                                    },
                                    "value": "0d0d9e0b-f2ef-42b4-8131-b5fa4f530086"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Workroom UI"
                                    },
                                    "value": "dd51de8b-6f12-47a4-94a8-73b090b0303e"
                                }
                            ]
                        }
                    }
                ],
                "submit": {
                    "type": "plain_text",
                    "text": "Submit"
                }
            }
        )
        return jsonify(response)
    except SlackApiError as e:
        return jsonify({"error": str(e.response['error'])})

@app.route("/slack/interactions", methods=["POST"])
def handle_interactions():
    payload = request.json
    if payload["type"] == "view_submission":
        view_data = payload["view"]["state"]["values"]

        title = view_data["title_block"]["title"]["value"]
        description = view_data["description_block"]["description"]["value"]
        component = view_data["component_block"]["component"]["selected_option"]["value"]

        user_id = payload["user"]["id"]
        user_info = slack_client.users_info(user=user_id)
        email = user_info['user']['profile']['email']

        # Here you'd call your backend function to submit this to Linear
        # submit_issue_to_linear(title, description, component, email)

        return jsonify({"response_action": "clear"})

    return jsonify({"status": "ok"})

def submit_issue_to_linear(title, description, component, email):
    """
    Submits an issue to Linear.

    :param title: The title of the issue
    :param description: The detailed description of the issue
    :param component: The ID of the component (label) selected by the user
    :param email: The email of the user reporting the issue
    """

    # The Linear API URL for creating an issue
    linear_url = "https://api.linear.app/graphql"

    # Prepare the headers, including the Linear API key
    headers = {
        "Authorization": os.getenv('LINEAR_API_KEY'),
        "Content-Type": "application/json"
    }

    # GraphQL mutation to create an issue in Linear
    mutation = {
        "query": """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    title
                }
            }
        }
        """,
        "variables": {
            "input": {
                "title": title,
                "description": f"{description}\n\nReported by: {email}",
                "teamId": os.getenv("LINEAR_TEAM_ID"),
                "labelIds": ["59f1342b-9ba3-4168-b3f6-a097a3de40af", component]  # Always include the fixed label ID
            }
        }
    }

    # Make the request to the Linear API
    response = requests.post(linear_url, json=mutation, headers=headers)

    # Handle the response
    if response.status_code == 200:
        result = response.json()
        if result.get("data", {}).get("issueCreate", {}).get("success"):
            print(f"Issue created successfully: {result['data']['issueCreate']['issue']['title']}")
        else:
            print("Failed to create issue in Linear.")
    else:
        print(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    app.run(port=3000)