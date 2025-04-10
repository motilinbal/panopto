# main_application.py

import os
import sys
import subprocess
import time
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
import requests
from dotenv import load_dotenv
# tenacity is recommended for robust retries as per plan.md, install with: pip install tenacity
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
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError, HttpResponseError

# --- Configuration & Setup ---

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("transcript_processing.log", encoding='utf-8') # Log to file
    ]
)

# Get configuration from environment variables with defaults
# Azure Credentials
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_INPUT_CONTAINER = os.getenv("AZURE_STORAGE_INPUT_CONTAINER", "mp3") # Defaulted based on testing
AZURE_SPEECH_API_KEY = os.getenv("AZURE_SPEECH_API_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "eastus") # Defaulted based on testing
# Local Paths
LOCAL_TEMP_AUDIO_DIR = os.getenv("LOCAL_TEMP_AUDIO_DIR", "./temp_audio/")
LOCAL_TRANSCRIPT_OUTPUT_DIR = os.getenv("LOCAL_TRANSCRIPT_OUTPUT_DIR", "./transcripts/")
# Timeouts & Polling
# Use client-level timeouts based on testing
CLIENT_CONNECTION_TIMEOUT_SECONDS = int(os.getenv("CLIENT_CONNECTION_TIMEOUT_SECONDS", 60))
CLIENT_READ_TIMEOUT_SECONDS = int(os.getenv("CLIENT_READ_TIMEOUT_SECONDS", 1900)) # Increased based on testing
POLLING_INTERVAL_SECONDS = int(os.getenv("POLLING_INTERVAL_SECONDS", 30))
MAX_POLLING_ATTEMPTS = int(os.getenv("MAX_POLLING_ATTEMPTS", 120)) # Default: 1 hour timeout (30s * 120)
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", 1800)) # 30 minutes for conversion
# Azure API Settings
API_VERSION = os.getenv("API_VERSION", "3.2")

# Validate essential configuration
if not all([AZURE_STORAGE_CONNECTION_STRING, AZURE_SPEECH_API_KEY, AZURE_SPEECH_REGION]):
    logging.error("Missing essential Azure credentials in .env file (AZURE_STORAGE_CONNECTION_STRING, AZURE_SPEECH_API_KEY, AZURE_SPEECH_REGION). Exiting.")
    sys.exit(1)

# Azure Speech API constants
SPEECH_BASE_URL = f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/speechtotext/{API_VERSION}"
SPEECH_HEADERS = {
    'Ocp-Apim-Subscription-Key': AZURE_SPEECH_API_KEY,
    'Content-Type': 'application/json'
}

# Create local directories if they don't exist
try:
    os.makedirs(LOCAL_TEMP_AUDIO_DIR, exist_ok=True)
    os.makedirs(LOCAL_TRANSCRIPT_OUTPUT_DIR, exist_ok=True)
except OSError as e:
    logging.error(f"Error creating local directories: {e}")
    sys.exit(1)

# --- Retry Strategy (Optional but Recommended) ---
# Define retry strategy for API calls using tenacity if available
if TENACITY_AVAILABLE:
    api_retry_strategy = retry(
        wait=wait_exponential(multiplier=1, min=2, max=10), # Exponential backoff: 2s, 4s, 8s, 10s...
        stop=stop_after_attempt(5), # Max 5 attempts for API calls
        retry=(
            retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError)) |
            retry_if_result(lambda r: isinstance(r, requests.Response) and r.status_code in [429, 500, 502, 503, 504]) # Retry on specific HTTP errors
        ),
        before_sleep=lambda retry_state: logging.warning(f"Retrying API call due to {retry_state.outcome.status_code if isinstance(retry_state.outcome, requests.Response) else type(retry_state.outcome).__name__}. Attempt #{retry_state.attempt_number}. Waiting {retry_state.next_action.sleep:.2f}s...")
    )
else:
    logging.warning("`tenacity` library not found. Proceeding without automatic API retries. Install with `pip install tenacity` for better robustness.")
    api_retry_strategy = retry() # Apply dummy decorator

# --- Helper Functions ---

def initialize_blob_service_client():
    """Initializes BlobServiceClient with configured timeouts."""
    logging.info(f"Initializing BlobServiceClient (Connect Timeout: {CLIENT_CONNECTION_TIMEOUT_SECONDS}s, Read Timeout: {CLIENT_READ_TIMEOUT_SECONDS}s)")
    try:
        client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING,
            connection_timeout=CLIENT_CONNECTION_TIMEOUT_SECONDS,
            read_timeout=CLIENT_READ_TIMEOUT_SECONDS
        )
        # Test connection lightly (optional, e.g., list containers if needed, but adds overhead)
        # client.list_containers(results_per_page=1).next()
        logging.info("BlobServiceClient initialized.")
        return client
    except Exception as e:
        logging.error(f"Failed to initialize Azure Blob Service Client: {e}")
        raise # Reraise to stop execution if client can't be created

def convert_m3u8_to_mp3(m3u8_url, output_mp3_path):
    """Converts M3U8 stream to MP3 using FFmpeg."""
    logging.info(f"Attempting FFmpeg conversion: {m3u8_url} -> {output_mp3_path}")
    command = [
        'ffmpeg',
        '-protocol_whitelist', 'file,http,https,tcp,tls,crypto',
        '-i', m3u8_url,
        '-acodec', 'mp3', '-ab', '128k',
        '-vn', '-y',
        '-loglevel', 'error',
        output_mp3_path
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
        logging.info(f"FFmpeg conversion successful for {m3u8_url}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg failed for {m3u8_url}. Return code: {e.returncode}. Stderr: {e.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        logging.error(f"FFmpeg timed out after {FFMPEG_TIMEOUT_SECONDS} seconds for {m3u8_url}")
        return False
    except FileNotFoundError:
        logging.error("FFmpeg command not found. Please ensure FFmpeg is installed and in system PATH.")
        # Consider exiting if FFmpeg is mandatory: sys.exit(1)
        return False
    except Exception as e:
        logging.error(f"Unexpected error during FFmpeg conversion for {m3u8_url}: {e}")
        return False

# Consider adding tenacity retry for upload if needed, though client timeouts help
def upload_blob(local_path, blob_name_in_azure, service_client):
    """Uploads a local file to Azure Blob Storage using the provided client."""
    logging.info(f"Uploading '{local_path}' to container '{AZURE_STORAGE_INPUT_CONTAINER}' as blob '{blob_name_in_azure}'...")
    if not os.path.exists(local_path):
        logging.error(f"Local file not found for upload: {local_path}")
        return False
    try:
        blob_client = service_client.get_blob_client(container=AZURE_STORAGE_INPUT_CONTAINER, blob=blob_name_in_azure)
        with open(local_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        logging.info(f"Upload successful for blob '{blob_name_in_azure}'.")
        return True
    except HttpResponseError as e:
        logging.error(f"Azure HTTP error during upload of '{blob_name_in_azure}': {e.message}")
        return False
    except Exception as e:
        err_str = str(e).lower()
        if "timeout" in err_str or "timed out" in err_str:
             logging.error(f"Upload operation timed out for '{blob_name_in_azure}' (Client Read Timeout: {CLIENT_READ_TIMEOUT_SECONDS}s).")
        else:
             logging.error(f"Unexpected error during upload of '{blob_name_in_azure}': {e}")
        return False

def get_blob_sas_uri(blob_name_in_azure, service_client):
    """Generates a read-only SAS URI for a blob."""
    logging.info(f"Generating SAS URI for blob '{blob_name_in_azure}'...")
    try:
        sas_token = generate_blob_sas(
            account_name=service_client.account_name,
            container_name=AZURE_STORAGE_INPUT_CONTAINER,
            blob_name=blob_name_in_azure,
            account_key=service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=3) # Extend expiry slightly
        )
        sas_uri = f"https://{service_client.account_name}.blob.core.windows.net/{AZURE_STORAGE_INPUT_CONTAINER}/{blob_name_in_azure}?{sas_token}"
        logging.info(f"SAS URI generated successfully for '{blob_name_in_azure}'.")
        return sas_uri
    except Exception as e:
        logging.error(f"Failed to generate SAS URI for '{blob_name_in_azure}': {e}")
        return None

def delete_blob(blob_name_in_azure, service_client):
    """Deletes a blob from Azure Blob Storage."""
    logging.info(f"Attempting cleanup: Deleting blob '{blob_name_in_azure}'...")
    if not blob_name_in_azure:
        logging.warning("Skipping blob deletion, blob name not provided.")
        return False
    try:
        blob_client = service_client.get_blob_client(container=AZURE_STORAGE_INPUT_CONTAINER, blob=blob_name_in_azure)
        blob_client.delete_blob(delete_snapshots="include")
        logging.info(f"Blob '{blob_name_in_azure}' deleted successfully.")
        return True
    except ResourceNotFoundError:
        logging.warning(f"Blob '{blob_name_in_azure}' not found for deletion (already deleted?).")
        return True # Treat as success if already gone
    except HttpResponseError as e:
        logging.error(f"Azure HTTP error during deletion of '{blob_name_in_azure}': {e.message}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error during blob deletion for '{blob_name_in_azure}': {e}")
        return False

@api_retry_strategy
def _make_speech_api_request(method, url, headers=None, json_payload=None, timeout=60):
    """Internal helper to make requests with retry."""
    response = requests.request(method, url, headers=headers, json=json_payload, timeout=timeout)
    response.raise_for_status() # Will raise HTTPError for 4xx/5xx, triggering retry if applicable
    return response

def submit_transcription_job(sas_uri, job_base_name):
    """Submits a transcription job to Azure Speech API."""
    logging.info(f"Submitting transcription job '{job_base_name}'...")
    job_display_name = f"{job_base_name}_{uuid.uuid4().hex[:8]}"
    endpoint_url = f"{SPEECH_BASE_URL}/transcriptions"
    payload = {
      "contentUrls": [sas_uri], "locale": "he-IL", "displayName": job_display_name,
      "properties": {"wordLevelTimestampsEnabled": True} # Add other properties if needed
    }
    try:
        response = _make_speech_api_request("POST", endpoint_url, headers=SPEECH_HEADERS, json_payload=payload)
        response_data = response.json()
        job_url = response_data.get('self')
        if not job_url:
            logging.error(f"Azure Speech API did not return a 'self' URL. Response: {response_data}")
            return None
        logging.info(f"Job submitted successfully. Job URL: {job_url}")
        return job_url
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to submit job for '{job_base_name}' after retries: {e}")
        if e.response is not None:
             logging.error(f"Final status code: {e.response.status_code}, Response body: {e.response.text}")
             if e.response.status_code == 400 and "InvalidSubscription" in e.response.text:
                  logging.error(">>> Ensure Azure Speech resource is on Standard (S0) pricing tier! <<<")
        return None
    except Exception as e:
         logging.error(f"Unexpected error submitting job '{job_base_name}': {e}")
         return None

def poll_job_status(job_url):
    """Polls the job status URL until completion or timeout."""
    logging.info(f"Polling job status every {POLLING_INTERVAL_SECONDS}s (Max {MAX_POLLING_ATTEMPTS} attempts): {job_url}")
    job_data = None; final_status = None; attempts = 0
    while attempts < MAX_POLLING_ATTEMPTS:
        attempts += 1
        logging.info(f"Polling attempt {attempts}/{MAX_POLLING_ATTEMPTS} for job {job_url.split('/')[-1]}...")
        try:
            if attempts > 1: time.sleep(POLLING_INTERVAL_SECONDS)
            # Use internal helper for retry logic on polling GET request
            response = _make_speech_api_request("GET", job_url, headers=SPEECH_HEADERS, timeout=30)
            job_data = response.json(); current_status = job_data.get('status')
            logging.info(f"  Job status: {current_status}")
            if current_status in ['Succeeded', 'Failed']:
                final_status = current_status; break
        except requests.exceptions.RequestException as e:
            logging.warning(f"Polling attempt {attempts} failed: {e}")
            if e.response is not None and e.response.status_code == 404:
                 logging.error("Job URL not found (404). Stopping poll."); final_status = 'NotFound'; break
            # Let retry handle transient issues, but break if max attempts reached after error
            if attempts >= MAX_POLLING_ATTEMPTS: final_status = 'PollingError'; break
        except Exception as e:
            logging.error(f"Unexpected polling error: {e}. Stopping poll."); final_status = 'PollingError'; break

    if final_status not in ['Succeeded', 'Failed', 'NotFound', 'PollingError']:
        logging.warning(f"Polling stopped after {max_polling_attempts} attempts. Job may still be running.")
        final_status = 'Timeout'
    return final_status, job_data

def download_transcript_content(job_data):
    """Downloads the transcript JSON content if job succeeded."""
    logging.info("Attempting to download transcript content...")
    if not job_data: logging.error("No job data available."); return None
    files_url = job_data.get('links', {}).get('files')
    if not files_url: logging.error(f"No 'files' link in job data: {job_data}"); return None

    try:
        logging.info(f"Getting file list from files URL...");
        files_response = _make_speech_api_request("GET", files_url, headers=SPEECH_HEADERS, timeout=30)
        files_data = files_response.json()

        transcript_content_url = next((f.get('links', {}).get('contentUrl') for f in files_data.get('values', []) if f.get('kind') == 'Transcription'), None)
        if not transcript_content_url: logging.error(f"Transcript 'contentUrl' not found in files list: {files_data}"); return None

        logging.info(f"Downloading transcript content from SAS URL...");
        # Download from SAS URL usually doesn't need auth headers, use simple requests.get with retry
        @api_retry_strategy # Apply retry to content download as well
        def download_sas_content(url):
             response = requests.get(url, timeout=120) # Longer timeout for potential large transcript download
             response.raise_for_status()
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
        # Use corrected parsing logic based on testing
        phrases = transcript_content.get('combinedRecognizedPhrases', [])
        full_text = " ".join([p.get('lexical', '') for p in phrases if p.get('lexical')]).strip()

        if not full_text: # Add fallback check if primary parsing yields nothing
             logging.warning("Primary parsing (combinedRecognizedPhrases/lexical) yielded empty text. Checking other fields...")
             # Add other potential fallbacks here if needed, e.g., displayText, recognizedPhrases/display
             if 'displayText' in transcript_content:
                  full_text = transcript_content['displayText'].strip()

        if full_text:
            logging.info(f"Extracted text length: {len(full_text)} characters.")
            output_dir = os.path.dirname(output_file_path)
            if output_dir: os.makedirs(output_dir, exist_ok=True) # Ensure output dir exists

            with open(output_file_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            logging.info(f"Transcript successfully saved to {output_file_path}")
            return True
        else:
            # If still no text, save raw JSON for debugging
            logging.error("Could not extract any text from transcript JSON.")
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

def cleanup_local_file(file_path):
    """Deletes a local file, logging outcome."""
    logging.info(f"Attempting cleanup: Deleting local file '{file_path}'...")
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Local file '{file_path}' deleted successfully.")
            return True
        else:
            logging.warning(f"Local file '{file_path}' not found for deletion.")
            return True # Not an error if it doesn't exist
    except OSError as e:
        logging.error(f"Failed to delete local file '{file_path}': {e}")
        return False
    except Exception as e:
         logging.error(f"Unexpected error deleting local file '{file_path}': {e}")
         return False

# --- Main Execution Logic ---

def main(input_file_path):
    """Main function to process the input file."""
    logging.info(f"--- Starting Batch Processing ---")
    logging.info(f"Input file: {input_file_path}")
    logging.info(f"Temporary audio dir: {LOCAL_TEMP_AUDIO_DIR}")
    logging.info(f"Transcript output dir: {LOCAL_TRANSCRIPT_OUTPUT_DIR}")

    try:
        blob_service_client = initialize_blob_service_client()
    except Exception:
        logging.critical("Failed to initialize Azure Blob Service Client. Cannot proceed.")
        sys.exit(1)

    # Read input file
    try:
        with open(input_file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logging.error(f"Input file not found: {input_file_path}"); sys.exit(1)
    except Exception as e:
        logging.error(f"Error reading input file {input_file_path}: {e}"); sys.exit(1)

    if len(lines) % 2 != 0:
        logging.warning("Input file has an odd number of lines. Processing pairs, last line may be ignored.")

    total_items = len(lines) // 2
    success_count = 0
    error_count = 0

    # Process lines in pairs (output_filename, m3u8_url)
    for i in range(0, len(lines) -1, 2):
        item_num = (i // 2) + 1
        output_base_filename = lines[i]
        m3u8_url = lines[i+1]

        logging.info(f"\n=== Processing Item {item_num}/{total_items}: {output_base_filename} ===")
        logging.info(f"M3U8 URL: {m3u8_url}")

        # Define paths and names for this item
        job_id_part = uuid.uuid4().hex[:8] # Short unique ID part
        temp_mp3_filename = f"{job_id_part}_{output_base_filename}.mp3"
        temp_mp3_path = os.path.join(LOCAL_TEMP_AUDIO_DIR, temp_mp3_filename)
        # Use original filename from input for the final transcript
        output_transcript_path = os.path.join(LOCAL_TRANSCRIPT_OUTPUT_DIR, f"{output_base_filename}.txt")
        blob_name = temp_mp3_filename # Use the same unique name for the blob
        job_base_name = f"transcript_{output_base_filename}"

        # Variables to track state for cleanup
        mp3_created = False
        blob_uploaded_name = None
        job_url = None

        try:
            # 1. Convert M3U8 to MP3
            if not convert_m3u8_to_mp3(m3u8_url, temp_mp3_path):
                raise RuntimeError(f"FFmpeg conversion failed for {m3u8_url}")
            mp3_created = True

            # 2. Upload MP3 to Azure Blob Storage
            if not upload_blob(temp_mp3_path, blob_name, blob_service_client):
                 raise RuntimeError(f"Failed to upload blob: {blob_name}")
            blob_uploaded_name = blob_name # Mark blob as uploaded for cleanup

            # 3. Get SAS URI for the blob
            sas_uri = get_blob_sas_uri(blob_uploaded_name, blob_service_client)
            if not sas_uri:
                raise RuntimeError(f"Failed to get SAS URI for blob: {blob_uploaded_name}")

            # 4. Submit Azure Speech Transcription Job
            job_url = submit_transcription_job(sas_uri, job_base_name)
            if not job_url:
                raise RuntimeError(f"Failed to submit transcription job for {job_base_name}")

            # 5. Polling Loop for Job Completion
            final_status, job_data = poll_job_status(job_url)

            # 6. Result Handling & Saving
            if final_status == 'Succeeded':
                logging.info("Job succeeded. Retrieving and saving transcript...")
                transcript_content = download_transcript_content(job_data)
                if transcript_content:
                    if save_transcript_to_file(transcript_content, output_transcript_path):
                        success_count += 1
                        logging.info(f"Successfully processed and saved transcript for '{output_base_filename}'.")
                    else:
                        raise RuntimeError("Failed to save the downloaded transcript.")
                else:
                     raise RuntimeError("Failed to download transcript content after job success.")
            elif final_status == 'Failed':
                error_details = job_data.get('error', {}) if job_data else {}
                logging.error(f"Transcription job failed for '{output_base_filename}'. Details: {error_details}")
                raise RuntimeError(f"Transcription job failed. Details: {error_details}")
            else: # Timeout, PollingError, NotFound etc.
                 logging.error(f"Job for '{output_base_filename}' did not succeed. Final status: {final_status}")
                 raise RuntimeError(f"Job did not succeed. Final status: {final_status}")

        except Exception as e:
            logging.error(f"--- Error processing item '{output_base_filename}': {e} ---")
            error_count += 1
            # Continue to the next item in the input file

        finally:
            # 7. Cleanup for this item
            logging.info(f"--- Cleaning up for item: {output_base_filename} ---")
            if blob_uploaded_name:
                delete_blob(blob_uploaded_name, blob_service_client)
            else:
                 logging.info(f"Skipping blob deletion as upload may not have occurred for {blob_name}.")
            if mp3_created:
                cleanup_local_file(temp_mp3_path)
            else:
                 logging.info(f"Skipping local MP3 deletion as conversion may not have occurred for {temp_mp3_path}.")
            # Optional: Delete completed/failed job record from Azure Speech service
            # if job_url and final_status in ['Succeeded', 'Failed']:
            #    try:
            #        logging.info(f"Deleting speech job record: {job_url}")
            #        _make_speech_api_request("DELETE", job_url, headers=SPEECH_HEADERS, timeout=30)
            #    except Exception as del_e:
            #        logging.warning(f"Failed to delete speech job record {job_url}: {del_e}")

    logging.info("\n--- Batch Processing Complete ---")
    logging.info(f"Total items in input: {total_items}")
    logging.info(f"Successfully processed: {success_count}")
    logging.info(f"Items with errors: {error_count}")
    logging.info("------------------------------")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"\nUsage: python {os.path.basename(__file__)} <input_file_path>")
        print("\nInput file should contain alternating lines:")
        print("output_filename_without_extension_1")
        print("m3u8_url1")
        print("output_filename_without_extension_2")
        print("m3u8_url2")
        print("...")
        print("\nRequires a .env file with Azure credentials.")
        print("Requires FFmpeg installed and in system PATH.")
        sys.exit(1)

    input_file = sys.argv[1]
    main(input_file)