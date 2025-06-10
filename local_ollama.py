from ollama import chat
import json
import os
import time

MODEL_NAME = "llama3.2"
INPUT_FILE = "./slack_messages.json"
OUTPUT_FILE = "output_analysis.json"

prompt_template = """
You are an AI assistant helping to analyze support or product issue messages.
Given the message below, extract the following in JSON format:

{{
  "summary_subject": "Short subject line for the issue",
  "summary": "Detailed technical summary of the issue(s)",
  "customers": ["List of customer names"],
  "sentiment": "positive" | "neutral" | "negative",
  "isFeedback": "Yes" or "No",
  "isRelatedtoMigration": "Yes" or "No"
}}
isRelatedtoMigration is If the thread is related to migration or it blocks migration or import of data from one source to another - mark this field as Yes otherwise No
Respond in valid JSON only.
Message:
\"\"\"
{text}
\"\"\"
"""

def main():
    with open(INPUT_FILE, 'r') as f:
        data = json.load(f)

    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'w') as f:
            json.dump([], f)

    batch_results = []

    for idx, item in enumerate(data, start=1):
        text = item.get('text', '')
        prompt = prompt_template.format(text=text)
        print(f"Processing message {idx}...")

        try:
            response = chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )
            output = response.message.content
        except Exception as e:
            print(f"Error querying Ollama for message {idx}: {e}")
            continue

        try:
            json_output = json.loads(output)
            batch_results.append(json_output)
            print(f"✅ Parsed message {idx}")
        except json.JSONDecodeError:
            print(f"⚠️ Failed to parse JSON from message {idx}: {output}")
            continue

        if idx % 10 == 0 or idx == len(data):
            with open(OUTPUT_FILE, 'r') as f:
                existing = json.load(f)
            existing.extend(batch_results)
            with open(OUTPUT_FILE, 'w') as f:
                json.dump(existing, f, indent=2)
            batch_results = []
            time.sleep(10)

    print("✅ Full analysis complete.")

if __name__ == "__main__":
    main()
