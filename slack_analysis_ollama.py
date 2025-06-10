import os
import json
import logging
import time
import datetime
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load tokens (prefer environment variables)
SLACK_BOT_TOKEN =os.getenv("SLACK_BOT_TOKEN")
OLLAMA_MODEL = "llama3.2"  # default to llama3
OLLAMA_URL = "http://localhost:11434"

if not SLACK_BOT_TOKEN:
    logging.error("SLACK_BOT_TOKEN is not set.")
    exit(1)

# Initialize Slack client
slack_client = WebClient(token=SLACK_BOT_TOKEN)

def fetch_last_n_threads(channel_id, n=5):
    try:
        threads = []
        cursor = None

        while len(threads) < n:
            response = slack_client.conversations_history(
                channel=channel_id,
                limit=100,
                cursor=cursor
            )
            messages = response["messages"]
            if not messages:
                break

            messages.sort(key=lambda m: float(m["ts"]), reverse=True)

            for message in messages:
                if len(threads) >= n:
                    break
                if "reply_count" in message and message["reply_count"] > 0:
                    thread_ts = message["ts"]
                    try:
                        thread = slack_client.conversations_replies(channel=channel_id, ts=thread_ts)
                        threads.append(thread["messages"])
                    except SlackApiError as e:
                        logging.error(f"Error fetching thread replies: {e.response['error']}")
                    time.sleep(1)

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return threads

    except SlackApiError as e:
        logging.error(f"Slack API error: {e.response['error']}")
        return []

def analyze_thread_for_issues(thread_messages):
    combined_text = "\n".join([msg.get("text", "") for msg in thread_messages])

    allowed_products = [
        "Ally", "Accessibility", "App Automate", "App Percy", "App Live", "Automate", "Automate TurboScale",
        "ATS", "Central Scanner", "SDK", "LCA", "Live", "Local", "Percy", "Test Management",
        "Test Observability", "O11Y", "Web A11Y", "App A11Y", "App LCA"
    ]

    product_list_str = ", ".join(f'"{p}"' for p in allowed_products)

    prompt = f"""
You are a technical support analyst. Carefully read the following Slack thread and extract detailed information to help engineering and support teams take swift action.

Focus on identifying:
- Root causes
- Technical symptoms
- Impacted services/features
- Any references to past incidents or existing bugs
- Any troubleshooting already attempted

Return a **strictly structured JSON** object with the following fields:

- summary_subject: A concise, 8–10 word title describing the key issue (e.g., "Login fails for App Live on iOS")
- summary: A comprehensive **technical summary** that explains:
    - What the problem is
    - When and how it was discovered
    - Who it affects (users/customers)
    - Any error messages, logs, or failing components
    - Relevant steps already taken to investigate
    - Any implications for reliability, performance, or UX
- products: Product name(s) involved — ONLY pick from this list: [{product_list_str}]
- customers: Customer name(s) explicitly mentioned or clearly implied
- sentiment: Overall customer sentiment — one of: "positive", "neutral", or "negative"

Only respond with a **pure JSON object**, no explanations, comments, or markdown formatting.

If you cannot find certain information, use empty values or defaults, like this:

{{
  "summary_subject": "",
  "summary": "",
  "products": [],
  "customers": [],
  "sentiment": "neutral"
}}

Slack thread content:
{combined_text}
"""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        result_text = response.json().get("response", "").strip()

        if result_text.startswith("```json"):
            result_text = result_text.strip("` \n")[len("json"):].strip()
        elif result_text.startswith("```"):
            result_text = result_text.strip("` \n")

        try:
            result_json = json.loads(result_text)
            return json.dumps(result_json, indent=2)
        except json.JSONDecodeError:
            logging.warning("Ollama response could not be parsed as JSON.")
            return result_text

    except Exception as e:
        logging.error(f"Ollama error: {e}")
        return f"Ollama error: {e}"

def main():
    channel_id = os.getenv("SLACK_CHANNEL_ID")
    logging.info(f"Fetching last 5 threads from channel: {channel_id}")
    threads = fetch_last_n_threads(channel_id, n=5)

    if not threads:
        logging.warning("No threads found or failed to fetch.")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"output_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        for i, thread in enumerate(threads):
            f.write(f"\n--- Thread {i + 1} ---\n")
            result = analyze_thread_for_issues(thread)
            f.write(result + "\n")

    logging.info(f"Analysis complete. Results saved to '{filename}'.")

if __name__ == "__main__":
    main()
