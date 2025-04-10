**Project Goal:** Develop a robust and efficient single Python script for converting M3U8 streams to Hebrew text transcripts via Azure Speech and Azure Blob Storage, using a polling mechanism for result retrieval.

**Guiding Principles:** Simplicity, robustness, clarity, leveraging Azure SDKs and best practices outlined in documentation.

---

**Detailed Development Plan:**

**Phase 1: Setup and Configuration**

1.  **Environment:**
    * Create a Python virtual environment (e.g., `python -m venv .venv` & `source .venv/bin/activate`).
    * Install necessary libraries:
        ```bash
        pip install python-dotenv azure-storage-blob requests tenacity
        ```
        * *Rationale:* Use `dotenv` for config management, `azure-storage-blob` SDK for reliable Blob interactions, `requests` for direct Azure Speech REST API calls, and `tenacity` for robust retries [cite: docs/plan.md].
2.  **Configuration (`.env` file):**
    * Create a `.env` file in the project root [cite: docs/overview.md].
    * Add required Azure credentials and settings as documented [cite: docs/azure_setup.md]:
        ```dotenv
        # Azure Storage Account
        AZURE_STORAGE_CONNECTION_STRING="<your_storage_connection_string>"
        AZURE_STORAGE_INPUT_CONTAINER="input" # Or your chosen container name

        # Azure Speech Service
        AZURE_SPEECH_API_KEY="<your_speech_service_key>"
        AZURE_SPEECH_REGION="<your_speech_service_region>" # e.g., eastus

        # Script Configuration
        LOCAL_TEMP_AUDIO_DIR="./temp_audio/"
        LOCAL_TRANSCRIPT_OUTPUT_DIR="./transcripts/"
        POLLING_INTERVAL_SECONDS=30
        MAX_POLLING_ATTEMPTS=120 # e.g., 30s * 120 = 1 hour timeout
        ```
    * Ensure this file is added to `.gitignore`.
3.  **Script Setup (`main_script.py`):**
    * Import necessary modules: `os`, `sys`, `subprocess`, `time`, `json`, `logging`, `uuid`, `datetime`, `timezone`, `requests`, `dotenv`, `tenacity`, `azure.storage.blob`, `azure.core.exceptions`.
    * Load environment variables using `dotenv.load_dotenv()`. Validate that required variables are present.
    * Configure logging using Python's `logging` module [cite: docs/config.py in docs/overview.md]. Set up a basic configuration logging to both console and a file (e.g., `processing.log`). Log timestamps, levels, and messages.
        ```python
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        # Optional: Add file handler
        ```
    * Define constants for Azure API version (e.g., `API_VERSION = "v3.2"`) and base URL [cite: docs/azure_speech_webhook.md, docs/azure_migration_plan.md].
        ```python
        AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
        AZURE_SPEECH_API_KEY = os.getenv("AZURE_SPEECH_API_KEY")
        API_VERSION = "3.2" # Or latest supported like 3.2
        SPEECH_BASE_URL = f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/speechtotext/{API_VERSION}"
        HEADERS = {
            'Ocp-Apim-Subscription-Key': AZURE_SPEECH_API_KEY,
            'Content-Type': 'application/json'
        }
        ```
    * Create local temporary and output directories if they don't exist.

**Phase 2: Core Function Implementation**

4.  **M3U8 Conversion Function:**
    * `def convert_m3u8_to_mp3(m3u8_url, output_mp3_path):`
    * Use `subprocess.run` to execute FFmpeg (preferred for flexibility) or VLC.
        ```python
        command = [
            'ffmpeg', '-i', m3u8_url,
            '-acodec', 'mp3', '-ab', '128k', # Example settings
            '-vn', # No video
            '-y', # Overwrite output without asking
            output_mp3_path
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=600) # Add timeout
            logging.info(f"FFmpeg conversion successful for {m3u8_url}")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg failed for {m3u8_url}: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
             logging.error(f"FFmpeg timed out for {m3u8_url}")
             return False
        except FileNotFoundError:
            logging.error("FFmpeg command not found. Is it installed and in PATH?")
            sys.exit(1) # Exit if core tool is missing
        ```
    * Include robust error handling: check return code, capture stderr, handle `FileNotFoundError` (if ffmpeg isn't installed), add a timeout.
5.  **Azure Blob Storage Functions:**
    * Initialize `BlobServiceClient` once:
        ```python
        blob_service_client = azure.storage.blob.BlobServiceClient.from_connection_string(os.getenv("AZURE_STORAGE_CONNECTION_STRING"))
        container_name = os.getenv("AZURE_STORAGE_INPUT_CONTAINER")
        ```
    * `def upload_to_blob(local_file_path, blob_name):`
        * Use `blob_service_client.get_blob_client(container=container_name, blob=blob_name)`
        * Call `blob_client.upload_blob(data, overwrite=True)` within a `with open(...) as data:` block.
        * Handle potential `azure.core.exceptions.ResourceExistsError`, `HttpResponseError`.
    * `def get_blob_sas_uri(blob_name):`
        * Use `azure.storage.blob.generate_blob_sas()` [cite: docs/azure_migration_plan.md].
        * Set `permission=azure.storage.blob.BlobSasPermissions(read=True)`.
        * Set expiry (e.g., `expiry=datetime.now(timezone.utc) + timedelta(hours=1)`) [cite: docs/azure_migration_plan.md].
        * Construct the full SAS URL: `f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"`
        * Handle potential errors during generation.
    * `def delete_blob(blob_name):`
        * Use `blob_service_client.delete_blob(container=container_name, blob=blob_name)`.
        * Handle potential `azure.core.exceptions.ResourceNotFoundError`.
6.  **Azure Speech API Functions (using `requests` and `tenacity`):**
    * Define retry strategy using `tenacity`:
        ```python
        retry_strategy = tenacity.retry(
            wait=tenacity.wait_exponential(multiplier=1, min=2, max=10), # Exponential backoff
            stop=tenacity.stop_after_attempt(5), # Max 5 attempts
            retry=tenacity.retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)) | tenacity.retry_if_result(lambda r: r.status_code in [429, 500, 502, 503, 504]) # Retry on specific errors/status codes
        )
        ```
    * Apply `@retry_strategy` decorator to API call functions.
    * `@retry_strategy def submit_transcription_job(audio_sas_uri, job_name):`
        * URL: `f"{SPEECH_BASE_URL}/transcriptions"` [cite: docs/azure_speech_webhook.md].
        * Method: `POST`.
        * Payload: `{ "contentUrls": [audio_sas_uri], "locale": "he-IL", "displayName": job_name, "properties": { "wordLevelTimestampsEnabled": True } }` [cite: docs/azure_speech_webhook.md, docs/azure_migration_plan.md].
        * Call `requests.post(url, headers=HEADERS, json=payload)`. Check `response.raise_for_status()`.
        * Return `response.json().get('self')`. Handle `KeyError` if 'self' is missing.
    * `@retry_strategy def get_job_status(job_url):`
        * URL: `job_url` (passed as argument) [cite: docs/azure_speech_webhook.md].
        * Method: `GET`.
        * Call `requests.get(job_url, headers=HEADERS)`. Check `response.raise_for_status()`.
        * Return `response.json()`. Handle potential JSON decoding errors.
    * `@retry_strategy def get_job_files(files_url):`
        * URL: `files_url` (extracted from job status response) [cite: docs/azure_speech_webhook.md].
        * Method: `GET`.
        * Call `requests.get(files_url, headers=HEADERS)`. Check `response.raise_for_status()`.
        * Return `response.json()`.
    * `@retry_strategy def download_file_content(content_url):`
        * URL: `content_url` (SAS URI for the transcript file) [cite: docs/azure_speech_webhook.md].
        * Method: `GET`.
        * Call `requests.get(content_url)`. Check `response.raise_for_status()`.
        * Return `response.json()`.

**Phase 3: Main Processing Logic**

7.  **Input File Handling:**
    * Read input file path from command line arguments (`sys.argv`).
    * Read the file line by line, extracting filename and M3U8 URL pairs (assuming alternating lines as per `plan.md`). Store them in a list of tuples or dictionaries. Handle potential file reading errors.
8.  **Main Loop:**
    * Iterate through the list of jobs (filename/URL pairs).
    * Inside the loop, use a `try...except...finally` block for each job to ensure cleanup is attempted.
    * Generate unique IDs/paths for this specific job (e.g., using `uuid.uuid4().hex`).
        ```python
        job_id = uuid.uuid4().hex
        base_filename = pair['filename'] # From input file
        temp_mp3_path = os.path.join(os.getenv("LOCAL_TEMP_AUDIO_DIR"), f"{job_id}.mp3")
        output_transcript_path = os.path.join(os.getenv("LOCAL_TRANSCRIPT_OUTPUT_DIR"), f"{base_filename}.txt")
        blob_name = f"{job_id}.mp3"
        ```
    * **Execute Steps:** Call the helper functions in sequence:
        * `convert_m3u8_to_mp3` -> `upload_to_blob` -> `get_blob_sas_uri` -> `submit_transcription_job`. Check return values/handle failures at each step. If a step fails, log error and `continue` to the next job in the input file (within the `except` block perhaps, after cleanup attempt in `finally`). Store the `job_url`.
    * **Polling Implementation:**
        ```python
        attempts = 0
        final_status = None
        job_data = None
        while attempts < int(os.getenv("MAX_POLLING_ATTEMPTS", 120)):
            attempts += 1
            logging.info(f"Polling attempt {attempts} for job {job_url}")
            try:
                job_data = get_job_status(job_url)
                final_status = job_data.get('status')
                if final_status in ['Succeeded', 'Failed']:
                    logging.info(f"Job {job_url} finished with status: {final_status}")
                    break
                elif final_status == 'Running':
                     logging.info(f"Job {job_url} is still running.")
                else:
                     logging.warning(f"Job {job_url} has status: {final_status}") # Or handle other statuses

                time.sleep(int(os.getenv("POLLING_INTERVAL_SECONDS", 30)))

            except requests.exceptions.RequestException as e:
                logging.error(f"Error polling job status for {job_url}: {e}")
                # Optional: Implement break after consecutive polling errors
                time.sleep(int(os.getenv("POLLING_INTERVAL_SECONDS", 30))) # Wait before retrying poll
            except Exception as e:
                 logging.exception(f"Unexpected error during polling for {job_url}") # Log stack trace
                 final_status = 'PollingError' # Indicate an issue with polling itself
                 break # Exit loop on unexpected error

        if final_status not in ['Succeeded', 'Failed']:
             logging.error(f"Job {job_url} did not complete within timeout. Last status: {final_status}")
             # Decide how to handle timeout - maybe leave blob?
        ```
    * **Result Retrieval & Saving (if `final_status == 'Succeeded'`):**
        * Extract `files_url = job_data.get('links', {}).get('files')`. Check if None.
        * Call `get_job_files(files_url)`.
        * Iterate through `files_data.get('values', [])` to find the transcript file (`kind == 'Transcription'`). Extract `content_url` [cite: docs/azure_speech_webhook.md].
        * Call `download_file_content(content_url)`.
        * Parse the `transcript_json`. Extract relevant text (e.g., iterate through `recognizedPhrases` or similar structure based on Azure's output format). Format it as required [cite: docs/plan.md].
        * Write the formatted text to `output_transcript_path`.
    * **Handle Failure (if `final_status == 'Failed'`):**
        * Log the error details found in `job_data.get('error', {})`.
    * **Cleanup (`finally` block):**
        * Attempt `delete_blob(blob_name)`. Log success/failure.
        * Attempt `os.remove(temp_mp3_path)`. Log success/failure.

**Phase 4: Testing and Refinement**

9.  **Testing:**
    * Test with valid M3U8 links.
    * Test with invalid/inaccessible M3U8 links.
    * Test with short and long audio files.
    * Test Azure credential errors (e.g., temporarily modify `.env`).
    * Test network interruptions during polling (if possible to simulate).
    * Verify transcript content and formatting.
    * Verify cleanup operations (check Azure portal and local folders).
10. **Refinement:** Adjust polling intervals, timeouts, error messages, and logging based on testing results. Add comments to explain complex sections. Ensure sensitive data (keys) are not logged.