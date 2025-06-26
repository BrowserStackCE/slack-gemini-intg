import json
import logging
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import google.generativeai as genai
from dotenv import load_dotenv
import os
from datetime import datetime, timezone

load_dotenv(override=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load tokens
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize clients if keys are present
if SLACK_BOT_TOKEN and GEMINI_API_KEY:
    slack_client = WebClient(token=SLACK_BOT_TOKEN)
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')

TIMESTAMP_FILE = "last_fetch_timestamp.txt"

def get_current_utc_timestamp():
    return str(datetime.now(timezone.utc).timestamp())

def read_last_timestamp():
    if os.path.exists(TIMESTAMP_FILE):
        with open(TIMESTAMP_FILE, "r") as f:
            return f.read().strip()
    return None

def write_current_timestamp(timestamp):
    with open(TIMESTAMP_FILE, "w") as f:
        f.write(timestamp)

def fetch_last_n_threads(channel_id):
    try:
        threads = []
        cursor = None

        current_ts = get_current_utc_timestamp()
        previous_ts = read_last_timestamp()

        if not previous_ts:
            logging.info("No previous timestamp found, using current time minus 1 hour as fallback.")
            previous_ts = str(float(current_ts) - 3600)

        logging.info(f"Fetching all threads between {previous_ts} and {current_ts}")

        while True:
            response = slack_client.conversations_history(
                channel=channel_id,
                limit=100,
                cursor=cursor,
                oldest=previous_ts,
                latest=current_ts,
                inclusive=True
            )
            messages = response["messages"]
            if not messages:
                break

            messages.sort(key=lambda m: float(m["ts"]), reverse=True)

            for message in messages:
                if "reply_count" in message and message["reply_count"] > 0:
                    thread_ts = message["ts"]
                    try:
                        thread = slack_client.conversations_replies(channel=channel_id, ts=thread_ts)
                        permalink_resp = slack_client.chat_getPermalink(channel=channel_id, message_ts=thread_ts)
                        permalink = permalink_resp.get("permalink", "")
                        threads.append({"messages": thread["messages"], "permalink": permalink})
                    except SlackApiError as e:
                        logging.error(f"Error fetching thread or permalink: {e.response['error']}")
                    time.sleep(1)

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        write_current_timestamp(current_ts)
        return threads

    except SlackApiError as e:
        logging.error(f"Slack API error: {e.response['error']}")
        return []

def analyze_thread_for_issues(thread_messages, permalink):
    combined_text = "\n".join([msg.get("text", "") for msg in thread_messages])
    allowed_products = [
        "Ally", "Accessibility", "App Automate", "App Percy", "App Live", "Automate", "Automate TurboScale",
        "ATS", "Central Scanner", "SDK", "LCA", "Live", "Local", "Percy", "Test Management",
        "Test Observability", "O11Y", "Web A11Y", "App A11Y", "App LCA"
    ]

    product_list_str = ", ".join(f'"{p}"' for p in allowed_products)

    prompt = f"""
You're a technical assistant. Analyze the following Slack thread and extract the following:

- summary_subject
- summary
- products: Choose only from [{product_list_str}]
- customers
- sentiment: positive | neutral | negative

Return JSON only:

{{
  "summary_subject": "Short subject line",
  "summary": "Technical summary",
  "products": ["Product1"],
  "customers": ["CustomerA"],
  "sentiment": "neutral"
}}

Thread:
{combined_text}
"""

    try:
        response = gemini_model.generate_content(prompt)
        raw_output = getattr(response, "text", str(response)).strip()

        if raw_output.startswith("```json"):
            raw_output = raw_output.strip("` \n")[len("json"):].strip()
        elif raw_output.startswith("```"):
            raw_output = raw_output.strip("` \n")

        try:
            result_json = json.loads(raw_output)

            # Add Slack thread permalink to summary
            if result_json.get("summary"):
                result_json["summary"] += f"\n\n🔗 Slack thread: {permalink}"
            else:
                result_json["summary"] = f"🔗 Slack thread: {permalink}"

            return json.dumps(result_json, indent=2)
        except json.JSONDecodeError:
            logging.warning("Gemini response could not be parsed as JSON.")
            return raw_output

    except Exception as e:
        logging.error(f"Gemini error: {e}")
        return f"Gemini error: {e}"

def analyze_and_save_threads(channel_id):
    threads = fetch_last_n_threads(channel_id)

    if not threads:
        logging.warning("No threads found or failed to fetch.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"output_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        for i, thread_data in enumerate(threads):
            f.write(f"\n--- Thread {i + 1} ---\n")
            result = analyze_thread_for_issues(thread_data["messages"], thread_data["permalink"])
            f.write(result + "\n")

    logging.info(f"Analysis complete. Results saved to '{filename}'.")
    return filename
