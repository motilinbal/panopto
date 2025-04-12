# collect_transcript.py

import os
import sys
import time
import json
import logging
import requests
from dotenv import load_dotenv
# Optional: Install tenacity for robust retries: pip install tenacity
try:
    from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, retry_if_result
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    # Dummy decorator if tenacity is not installed
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# --- User Input ---
# TODO: Replace these values with the actual Job Name and Job ID you want to retrieve
JOB_NAME = "linear-algebra-tutorial-03-04-25" # Example: Use the name from input.txt
JOB_ID = "54d2c007-d1a6-4c9f-84af-edea84c95bd3" # Example: The ID from the logs
# --- End User Input ---

# --- Configuration & Setup ---

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
        # Optionally add a FileHandler if needed:
        # logging.FileHandler("collect_transcript.log", encoding='utf-8')
    ]
)

# --- Suppress verbose SDK logging ---
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
# --- End Suppress ---

# Get configuration from environment variables
AZURE_SPEECH_API_KEY = os.getenv("AZURE_SPEECH_API_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
# Use LOCAL_TRANSCRIPT_OUTPUT_DIR from .env for saving the final transcript
LOCAL_TRANSCRIPT_OUTPUT_DIR = os.getenv("LOCAL_TRANSCRIPT_OUTPUT_DIR", "./transcripts/")
POLLING_INTERVAL_SECONDS = int(os.getenv("POLLING_INTERVAL_SECONDS", 30))
MAX_POLLING_ATTEMPTS = int(os.getenv("MAX_POLLING_ATTEMPTS", 120))
API_VERSION = os.getenv("API_VERSION", "v3.2") # Ensure this matches the version used for job submission

# Validate essential configuration
if not all([AZURE_SPEECH_API_KEY, AZURE_SPEECH_REGION]):
    logging.error("Missing essential Azure credentials in .env file (AZURE_SPEECH_API_KEY, AZURE_SPEECH_REGION). Exiting.")
    sys.exit(1)

if not JOB_ID:
    logging.error("JOB_ID is not set at the top of the script. Exiting.")
    sys.exit(1)

if not JOB_NAME:
    logging.warning("JOB_NAME is not set. The output file will be named based on JOB_ID.")
    # Use JOB_ID as fallback filename if JOB_NAME is empty
    JOB_NAME = JOB_ID

# Azure Speech API constants
SPEECH_BASE_URL = f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/speechtotext/{API_VERSION}"
SPEECH_HEADERS = {
    'Ocp-Apim-Subscription-Key': AZURE_SPEECH_API_KEY,
    'Content-Type': 'application/json' # Header needed for GET requests too sometimes
}

# Ensure output directory exists
try:
    os.makedirs(LOCAL_TRANSCRIPT_OUTPUT_DIR, exist_ok=True)
except OSError as e:
    logging.error(f"Error creating transcript output directory '{LOCAL_TRANSCRIPT_OUTPUT_DIR}': {e}")
    sys.exit(1)

# --- Retry Strategy (Copied from main.py [cite: 1]) ---
if TENACITY_AVAILABLE:
    api_retry_strategy = retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        retry=(
            retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError)) |
            retry_if_result(lambda r: isinstance(r, requests.Response) and r.status_code in [429, 500, 502, 503, 504])
        ),
        before_sleep=lambda retry_state: logging.warning(f"Retrying API call due to {retry_state.outcome.status_code if isinstance(retry_state.outcome, requests.Response) else type(retry_state.outcome).__name__}. Attempt #{retry_state.attempt_number}. Waiting {retry_state.next_action.sleep:.2f}s...")
    )
else:
    logging.warning("`tenacity` library not found. Proceeding without automatic API retries. Install with `pip install tenacity` for better robustness.")
    api_retry_strategy = retry()

# --- Helper Functions (Adapted from main.py [cite: 1]) ---

@api_retry_strategy
def _make_speech_api_request(method, url, headers=None, json_payload=None, data=None, timeout=60):
    """Internal helper to make requests with retry."""
    response = requests.request(method, url, headers=headers, json=json_payload, data=data, timeout=timeout)
    response.raise_for_status() # Raise HTTPError for 4xx/5xx
    return response

def poll_job_status(job_url):
    """Polls the job status URL until completion or timeout."""
    logging.info(f"Polling job status every {POLLING_INTERVAL_SECONDS}s (Max {MAX_POLLING_ATTEMPTS} attempts): {job_url}")
    job_data = None; final_status = None; attempts = 0
    while attempts < MAX_POLLING_ATTEMPTS:
        attempts += 1
        job_id_short = job_url.split('/')[-1]
        # logging.info(f"Polling attempt {attempts}/{MAX_POLLING_ATTEMPTS} for job {job_id_short}...")
        try:
            if attempts > 1: time.sleep(POLLING_INTERVAL_SECONDS)
            response = _make_speech_api_request("GET", job_url, headers=SPEECH_HEADERS, timeout=30)
            job_data = response.json(); current_status = job_data.get('status')
            logging.info(f"Polling attempt {attempts}/{MAX_POLLING_ATTEMPTS}: Job status is '{current_status}'")
            if current_status in ['Succeeded', 'Failed']:
                final_status = current_status; break
            # Check for other potential intermediate states if needed (e.g., 'Running', 'NotStarted')
            elif current_status not in ['Running', 'NotStarted']:
                 logging.warning(f"Unexpected job status encountered: {current_status}. Continuing poll.")

        except requests.exceptions.RequestException as e:
            logging.warning(f"Polling attempt {attempts} failed for job {job_id_short}: {e}")
            if e.response is not None and e.response.status_code == 404:
                 logging.error(f"Job URL {job_url} not found (404) during polling. Stopping poll."); final_status = 'NotFound'; break
            if attempts >= MAX_POLLING_ATTEMPTS: final_status = 'PollingError'; break
        except Exception as e:
            logging.error(f"Unexpected polling error for job {job_id_short}: {e}. Stopping poll."); final_status = 'PollingError'; break

    if final_status not in ['Succeeded', 'Failed', 'NotFound', 'PollingError']:
        logging.warning(f"Polling stopped after {MAX_POLLING_ATTEMPTS} attempts for job {job_id_short}. Final status check might have timed out.")
        # Attempt one last status check without waiting
        try:
            response = _make_speech_api_request("GET", job_url, headers=SPEECH_HEADERS, timeout=30)
            job_data = response.json(); current_status = job_data.get('status')
            logging.info(f"Final status check: Job status is '{current_status}'")
            if current_status in ['Succeeded', 'Failed']:
                 final_status = current_status
            else:
                 final_status = 'Timeout' # If still not done after max attempts
        except Exception as e:
            logging.error(f"Final status check failed: {e}")
            final_status = 'PollingError' # Error during final check

    return final_status, job_data

def download_transcript_content(job_data):
    """Downloads the transcript JSON content if job succeeded."""
    logging.info("Attempting to download transcript content...")
    if not job_data: logging.error("No job data available for download."); return None
    files_url = job_data.get('links', {}).get('files')
    if not files_url: logging.error(f"No 'files' link in job data: {job_data}"); return None

    try:
        logging.info(f"Getting file list from files URL: {files_url}");
        files_response = _make_speech_api_request("GET", files_url, headers=SPEECH_HEADERS, timeout=30)
        files_data = files_response.json()

        transcript_content_url = next((f.get('links', {}).get('contentUrl') for f in files_data.get('values', []) if f.get('kind') == 'Transcription'), None)
        if not transcript_content_url: logging.error(f"Transcript 'contentUrl' not found in files list: {files_data}"); return None

        logging.info(f"Downloading transcript content from SAS URL..."); # Avoid logging potentially sensitive SAS URL

        # Use simple requests.get for SAS URL, but reuse the retry wrapper for consistency
        @api_retry_strategy
        def download_sas_content(url):
             # Use the internal helper which has logging and error handling built-in
             response = _make_speech_api_request("GET", url, timeout=120) # Longer timeout for potential large transcript
             return response.json()

        transcript_json = download_sas_content(transcript_content_url)
        logging.info("Transcript content downloaded successfully.")
        return transcript_json

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download transcript files/content after retries: {e}")
        if e.response is not None: logging.error(f"Final status code: {e.response.status_code}, Response body: {e.response.text}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error during transcript download: {e}"); return None

def save_transcript_to_file(transcript_content, output_file_path):
    """Parses transcript JSON and saves formatted text to a file."""
    logging.info(f"Parsing and saving transcript to: {output_file_path}")
    if not transcript_content: logging.error("Cannot save transcript, content is empty."); return False

    try:
        # Attempt extraction using the primary structure from main.py [cite: 1]
        phrases = transcript_content.get('combinedRecognizedPhrases', [])
        full_text = " ".join([p.get('lexical', '') for p in phrases if p.get('lexical')]).strip()

        # Fallback if primary structure yields no text
        if not full_text:
             logging.warning("Primary parsing (combinedRecognizedPhrases/lexical) yielded empty text. Checking 'displayText'...")
             if 'displayText' in transcript_content:
                  full_text = transcript_content['displayText'].strip()

        if full_text:
            logging.info(f"Extracted text length: {len(full_text)} characters.")
            output_dir = os.path.dirname(output_file_path)
            if output_dir: os.makedirs(output_dir, exist_ok=True) # Ensure directory exists just in case

            with open(output_file_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            logging.info(f"Transcript successfully saved to {output_file_path}")
            return True
        else:
            logging.error("Could not extract any text from the transcript JSON content.")
            # Save raw JSON for debugging if text extraction fails
            raw_json_path = output_file_path + ".raw.json"
            try:
                 with open(raw_json_path, 'w', encoding='utf-8') as f_raw:
                     json.dump(transcript_content, f_raw, indent=2, ensure_ascii=False)
                 logging.info(f"Raw transcript JSON saved to {raw_json_path} for debugging.")
            except Exception as dump_e:
                 logging.error(f"Failed to save raw transcript JSON: {dump_e}")
            return False

    except Exception as e:
        logging.error(f"Error parsing/saving transcript content: {e}")
        return False

# --- Main Execution ---

def retrieve_transcript(job_name, job_id):
    """Retrieves and saves the transcript for a specific job ID."""
    logging.info(f"\n=== Attempting to retrieve transcript for Job Name: {job_name}, Job ID: {job_id} ===")

    # Construct the specific job URL
    job_url = f"{SPEECH_BASE_URL}/transcriptions/{job_id}"
    output_transcript_path = os.path.join(LOCAL_TRANSCRIPT_OUTPUT_DIR, f"{job_name}.txt")

    final_status, job_data = poll_job_status(job_url)

    if final_status == 'Succeeded':
        logging.info(f"Job '{job_id}' succeeded. Retrieving transcript...")
        transcript_content = download_transcript_content(job_data)
        if transcript_content:
            if save_transcript_to_file(transcript_content, output_transcript_path):
                logging.info(f"Successfully retrieved and saved transcript for job '{job_id}' to '{output_transcript_path}'.")
            else:
                logging.error(f"Failed to save the downloaded transcript for job '{job_id}'.")
        else:
             logging.error(f"Failed to download transcript content after job '{job_id}' success.")
    elif final_status == 'Failed':
        error_details = job_data.get('error', {}) if job_data else {}
        logging.error(f"Transcription job '{job_id}' failed. Details: {error_details}")
    elif final_status == 'NotFound':
         logging.error(f"Transcription job '{job_id}' could not be found at URL: {job_url}. Check Region, API Version, and Job ID.")
    else: # Timeout, PollingError etc.
         logging.error(f"Could not confirm success for job '{job_id}'. Final status: {final_status}. Transcript not downloaded.")

    logging.info(f"--- Finished processing job ID: {job_id} ---")

if __name__ == "__main__":
    # Make sure JOB_NAME and JOB_ID are set at the top of the script
    if not JOB_ID:
         logging.error("Please set the JOB_ID variable at the top of the script.")
    else:
         retrieve_transcript(JOB_NAME, JOB_ID)