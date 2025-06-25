import os
import json
import logging
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
JIRA_BASE_URL = ""
JIRA_EMAIL = ""
JIRA_API_TOKEN= ""
JIRA_PROJECT_KEY = ""
OUTPUT_FILENAME = ""

if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY, OUTPUT_FILENAME]):
    logging.error("One or more required environment variables are missing.")
    exit(1)

# JIRA auth
jira_auth = (JIRA_EMAIL, JIRA_API_TOKEN)
jira_headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# Helper to parse a single thread from the output file
def parse_threads_from_file(filename):
    threads = []
    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()
        thread_chunks = content.split("--- Thread")
        for chunk in thread_chunks:
            try:
                json_start = chunk.index("{")
                json_data = chunk[json_start:]
                parsed = json.loads(json_data)
                if parsed.get("summary_subject"):
                    threads.append(parsed)
            except (ValueError, json.JSONDecodeError):
                continue
    return threads

# Create a JIRA issue
def create_jira_issue(issue_data):
    issue_payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": issue_data["summary_subject"],
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": issue_data["summary"]
                            }
                        ]
                    }
                ]
            },
            "issuetype": {"name": "Ticket"},
            "labels": [p.lower().replace(" ", "_") for p in issue_data.get("products", [])],
            "customfield_10104": { "id": "10155" }, #source
            "customfield_10103": { "id": "10697" }  # Work category internal
        }
    }
    response = requests.post(
        f"{JIRA_BASE_URL}/rest/api/3/issue",
        auth=jira_auth,
        headers=jira_headers,
        data=json.dumps(issue_payload)
    )
    if response.status_code == 201:
        issue_key = response.json().get("key")
        logging.info(f"Created JIRA issue: {issue_key}")
    else:
        logging.error(f"Failed to create JIRA issue: {response.status_code} {response.text}")

# Main
if __name__ == "__main__":
    issues = parse_threads_from_file(OUTPUT_FILENAME)
    if not issues:
        logging.warning("No valid issues found in output file.")
        exit(0)

    logging.info(f"Found {len(issues)} issues to push to JIRA.")
    for issue in issues:
        create_jira_issue(issue)