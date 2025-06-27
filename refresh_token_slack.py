import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

ENV_FILE = ".env"

# Load environment variables from .env file
load_dotenv(ENV_FILE)

def check_env_vars():
    required_vars = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "REFRESH_TOKEN"]
    missing = False
    for var in required_vars:
        if not os.getenv(var):
            print(f"{var} is missing!")
            missing = True
    if missing:
        exit("One or more required environment variables are missing.")

def refresh_token():
    print("Requesting new access token from Slack...")
    url = "https://slack.com/api/oauth.v2.access"
    data = {
        "client_id": os.getenv("SLACK_CLIENT_ID"),
        "client_secret": os.getenv("SLACK_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": os.getenv("REFRESH_TOKEN")
    }

    response = requests.post(url, data=data)
    if response.status_code != 200:
        print("Slack API call failed:", response.text)
        exit(1)

    resp_json = response.json()
    access_token = resp_json.get("access_token")
    new_refresh_token = resp_json.get("refresh_token")

    if not access_token:
        print("Error: Failed to obtain access token!")
        print(json.dumps(resp_json, indent=2))
        exit(1)

    return access_token, new_refresh_token

def update_env_file(new_refresh_token):
    lines = Path(ENV_FILE).read_text().splitlines()
    updated_lines = []
    for line in lines:
        if line.startswith("REFRESH_TOKEN="):
            updated_lines.append(f"REFRESH_TOKEN={new_refresh_token}")
        else:
            updated_lines.append(line)
    Path(ENV_FILE).write_text("\n".join(updated_lines) + "\n")
    print("Updated .env file with new refresh token.")

def save_token_to_env_file(access_token):
    lines = Path(ENV_FILE).read_text().splitlines()
    updated_lines = []
    token_updated = False

    for line in lines:
        if line.startswith("SLACK_BOT_TOKEN="):
            updated_lines.append(f"SLACK_BOT_TOKEN={access_token}")
            token_updated = True
        else:
            updated_lines.append(line)

    if not token_updated:
        # Append if SLACK_BOT_TOKEN doesn't exist
        updated_lines.append(f"SLACK_BOT_TOKEN={access_token}")

    Path(ENV_FILE).write_text("\n".join(updated_lines) + "\n")
    print("SLACK_BOT_TOKEN updated in .env file.")


def refresh_slack_token():
    check_env_vars()
    access_token, new_refresh_token = refresh_token()
    save_token_to_env_file(access_token)
    if new_refresh_token:
        update_env_file(new_refresh_token)

