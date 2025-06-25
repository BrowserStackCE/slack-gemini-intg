import logging
from slack_thread_analysis import analyze_and_save_threads
from jira_ticket_creator import create_issues_from_file
from dotenv import load_dotenv
import os

load_dotenv(override=True)
# Setup logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main():
    SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID')
    
    if not SLACK_CHANNEL_ID:
        logging.error("SLACK_CHANNEL_ID is not set.")
        return

    # Step 1: Analyze threads and save output file
    output_file = analyze_and_save_threads(SLACK_CHANNEL_ID)

    # # Step 2: Use that file to create Jira issues
    if output_file:
        create_issues_from_file(output_file)
    else:
        logging.warning("No output file created. Skipping Jira issue creation.")

if __name__ == "__main__":
    main()
