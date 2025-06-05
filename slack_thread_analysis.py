import os
import json
import logging
import time
import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load tokens (prefer environment variables)
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not SLACK_BOT_TOKEN or not GEMINI_API_KEY:
    logging.error("SLACK_BOT_TOKEN or GEMINI_API_KEY is not set.")
    exit(1)

# Initialize clients
slack_client = WebClient(token=SLACK_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')

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

            # Sort messages by timestamp descending (newest first)
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
                    time.sleep(1)  # avoid rate limits

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
You're a technical assistant. Analyze the following Slack thread and extract the following:

- summary_subject: A crisp 8–10 word issue subject line (e.g., "Login fails for App Live on iOS")
- summary: A **detailed technical summary** of the main technical issue(s), including relevant context and impacted areas
- products: Product name(s) involved — ONLY choose from this list: [{product_list_str}]
- customers: Customer name(s) mentioned
- sentiment: Overall customer sentiment (e.g., positive, neutral, negative)

ONLY return a JSON object in the following format — no commentary or markdown:

{{
  "summary_subject": "Short subject line for the issue",
  "summary": "Detailed technical summary of the issue(s)",
  "products": ["List of product names from the allowed list"],
  "customers": ["List of customer names"],
  "sentiment": "positive" | "neutral" | "negative"
}}

If no relevant information is found, return empty values like this:

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
        response = gemini_model.generate_content(prompt)
        raw_output = getattr(response, "text", str(response)).strip()

        # Clean code block markdown if present
        if raw_output.startswith("```json"):
            raw_output = raw_output.strip("` \n")[len("json"):].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output.strip("` \n")

        try:
            result_json = json.loads(raw_output)
            return json.dumps(result_json, indent=2)
        except json.JSONDecodeError:
            logging.warning("Gemini response could not be parsed as JSON.")
            return raw_output

    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"Gemini error: {e}"


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
