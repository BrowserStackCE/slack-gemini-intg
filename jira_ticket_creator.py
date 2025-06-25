import os
import json
import logging
import requests
from dotenv import load_dotenv

# Load .env variables
load_dotenv(override=True)

# Logging config
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load Jira credentials
JIRA_BASE_URL = os.getenv('JIRA_BASE_URL')
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
JIRA_PROJECT_KEY = os.getenv('JIRA_PROJECT_KEY')

if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY]):
    logging.error("One or more required environment variables are missing.")
    exit(1)

jira_auth = (JIRA_EMAIL, JIRA_API_TOKEN)
jira_headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def load_allowed_customers(filepath="allowed_customers.txt"):
    allowed_set = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                cleaned = line.strip()
                # Ignore empty lines and section headers
                if not cleaned or cleaned.lower().startswith(("group id", "customer name")):
                    continue
                allowed_set.add(cleaned)
        logging.info(f"Loaded {len(allowed_set)} allowed customers/group IDs from {filepath}")
    except FileNotFoundError:
        logging.warning(f"Allowed customers file '{filepath}' not found.")
    return allowed_set

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
            "customfield_10104": {"id": "10155"},  # Update with real field ID
            "customfield_10103": {"id": "10697"}   # Update with real field ID
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
        logging.info(f"✅ Created JIRA issue: {issue_key}")
    else:
        logging.error(f"❌ Failed to create JIRA issue: {response.status_code} {response.text}")

def create_issues_from_file(filename):
    issues = parse_threads_from_file(filename)
    if not issues:
        logging.warning("No valid issues found in output file.")
        return

    allowed_customers = load_allowed_customers()
    logging.info(f"Found {len(issues)} issues to evaluate for JIRA.")

    for issue in issues:
        sentiment = issue.get("sentiment", "").lower()
        customers_list = issue.get("customers", [])

        group_id = None
        customer_name = None

        for entry in customers_list:
            if entry.lower().startswith("group id:"):
                group_id = entry.split(":", 1)[1].strip()
            else:
                customer_name = entry.strip()

        # Check: group ID or customer name in allowed list, or negative sentiment
        should_create = (
            sentiment == "negative" or
            (group_id and group_id in allowed_customers) or
            (customer_name and customer_name in allowed_customers)
        )

        if should_create:
            logging.info(f" Creating issue - Group: '{group_id}', Customer: '{customer_name}', Sentiment: '{sentiment}'")
            create_jira_issue(issue)
        else:
            logging.info(f" Skipping - Group: '{group_id}', Customer: '{customer_name}', Sentiment: '{sentiment}'")
