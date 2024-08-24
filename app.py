import os
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import requests
import logging
import json

load_dotenv()

app = Flask(__name__)

slack_token = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=slack_token)

@app.route("/slack/command", methods=["POST"])
def handle_command():
    trigger_id = request.form.get("trigger_id")
    text = request.form.get("text")  # This captures the text after the command

    # Use the text as the default title in the modal
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
                                "text": "Enter the issue title - one line only"
                            },
                            "initial_value": text  # Pre-fill the title with the text from the command
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
                                "text": "Enter a detailed description of how to reproduce the issue. More details are better!"
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

        return jsonify({"status": "success"})

    except SlackApiError as e:
        logging.error("Slack API Error: %s", e.response["error"])
        return jsonify({"error": str(e.response["error"])})

@app.route("/slack/interactions", methods=["POST"])
def handle_interactions():
    # Parse the URL-encoded form data
    payload = request.form.get("payload")
    
    if payload:
        # Convert the payload from JSON string to a Python dictionary
        payload = json.loads(payload)
        logging.info("Received interaction payload: %s", payload)

        if payload["type"] == "view_submission" and payload["view"]["callback_id"] == "issue_report_modal":
            try:
                view_data = payload["view"]["state"]["values"]
                title = view_data["title_block"]["title"]["value"]
                description = view_data["description_block"]["description"]["value"]
                component = view_data["component_block"]["component"]["selected_option"]["value"]

                user_id = payload["user"]["id"]
                user_info = slack_client.users_info(user=user_id)
                email = user_info['user']['profile']['email']

                # Submit the issue to Linear
                submit_issue_to_linear(title, description, component, email)

                return jsonify({"response_action": "clear"})

            except Exception as e:
                logging.error("Error processing interaction: %s", str(e))
                return jsonify({"error": "There was an error processing the interaction"}), 500

    return jsonify({"status": "ok"})

@app.route("/slack/events", methods=["POST"])
def slack_events():
    print("Received event")
    data = request.json

    # Slack's URL verification challenge
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    # Handle the app_mention event
    if data.get("event", {}).get("type") == "app_mention":
        event = data["event"]
        user_id = event["user"]
        text = event["text"]
        channel_id = event["channel"]
        thread_ts = event.get("thread_ts")

        try:
            # Retrieve the thread messages (if mentioned in a thread)
            if thread_ts:
                response = slack_client.conversations_replies(channel=channel_id, ts=thread_ts)
                messages = response["messages"]
                description = "\n".join([msg["text"] for msg in messages])
            else:
                description = text

            # Get the user's email
            user_info = slack_client.users_info(user=user_id)
            email = user_info['user']['profile']['email']

            # Remove the mention from the title
            title = text.replace(f"<@{data['authorizations'][0]['user_id']}>", "").strip()

            # Create the issue in Linear
            submit_issue_to_linear(title, description, None, email)

            # Respond in the thread or channel
            slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts if thread_ts else event["ts"],
                text="Issue created successfully from this conversation."
            )

        except SlackApiError as e:
            logging.error(f"Error creating issue: {e.response['error']}")

    return jsonify({"status": "ok"})

def submit_issue_to_linear(title, description, component=None, email=None):
    """
    Submits an issue to Linear.

    :param title: The title of the issue
    :param description: The detailed description of the issue
    :param component: The ID of the component (label) selected by the user (optional)
    :param email: The email of the user reporting the issue (optional)
    """

    # The Linear API URL for creating an issue
    linear_url = "https://api.linear.app/graphql"

    # Prepare the headers, including the Linear API key
    headers = {
        "Authorization": os.getenv('LINEAR_API_KEY'),
        "Content-Type": "application/json"
    }

    # Prepare the list of label IDs, including the fixed label ID
    label_ids = ["59f1342b-9ba3-4168-b3f6-a097a3de40af"]  # Fixed label ID
    if component:
        label_ids.append(component)

    # Prepare the input dictionary for the mutation
    input_data = {
        "title": title,
        "description": f"{description}\n\nReported by: {email}" if email else description,
        "teamId": os.getenv("LINEAR_TEAM_ID"),
    }

    # Only include labelIds if there are valid labels to include
    if label_ids:
        input_data["labelIds"] = label_ids

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
            "input": input_data
        }
    }

    # Make the request to the Linear API
    response = requests.post(linear_url, json=mutation, headers=headers)

    # Log the response status and content
    logging.info(f"Linear API Response Status Code: {response.status_code}")
    logging.info(f"Linear API Response Text: {response.text}")

    # Handle the response
    if response.status_code == 200:
        result = response.json()
        if result.get("data", {}).get("issueCreate", {}).get("success"):
            logging.info(f"Issue created successfully: {result['data']['issueCreate']['issue']['title']}")
        else:
            logging.error("Failed to create issue in Linear.")
            logging.error(f"Linear API Error: {result.get('errors', 'Unknown error')}")
    else:
        logging.error(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    app.run(port=3000)