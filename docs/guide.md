# Developer Guide: M3U8 to Hebrew Transcript Pipeline Insights

## 1. Introduction

This document summarizes key findings and technical considerations derived from iterative testing of the M3U8-to-Hebrew-transcript pipeline. The goal is to inform the development of the final, robust Python application based on the initial `overview.md` [cite: Panopto/overview.md] and `plan.md` [cite: Panopto/plan.md].

## 2. Dependencies

### 2.1. Python Libraries

Ensure the following libraries are included in `requirements.txt` and installed in the virtual environment:

* `requests`: For direct interaction with the Azure Speech REST API.
* `azure-storage-blob`: For Azure Blob Storage operations (upload, SAS generation, delete).
* `python-dotenv`: For managing configuration and credentials securely.
* `tenacity`: (As originally planned [cite: Panopto/plan.md]) For implementing robust retry logic, especially for API calls and potentially uploads.

### 2.2. External Tools

* **FFmpeg:** This is a critical external dependency.
    * It **must** be installed on the system running the script.
    * The directory containing the `ffmpeg` executable **must** be included in the system's `PATH` environment variable. Failure to find FFmpeg will cause the script to fail early.

## 3. Configuration (`.env` File)

* Store sensitive credentials securely using a `.env` file.
* **Required Variables:**
    * `AZURE_STORAGE_CONNECTION_STRING`: Full connection string for the storage account. Ensure it grants permissions for Write (upload), Delete (cleanup), and Generate SAS tokens.
    * `AZURE_STORAGE_INPUT_CONTAINER`: Name of the container for temporary MP3 uploads (e.g., `mp3`). **Ensure this container exists.**
    * `AZURE_SPEECH_API_KEY`: API key for the Azure Speech service.
    * `AZURE_SPEECH_REGION`: Region of the Azure Speech service (e.g., `eastus`).
* **Security:** Emphasize that these keys are sensitive. **Immediately regenerate any keys** if they are accidentally exposed.
* **Script Behavior Variables (Optional Overrides):**
    * `LOCAL_TEMP_AUDIO_DIR`, `LOCAL_TRANSCRIPT_OUTPUT_DIR`
    * `POLLING_INTERVAL_SECONDS`, `MAX_POLLING_ATTEMPTS` (See Polling section below).

## 4. Core Workflow & Implementation Notes

### 4.1. M3U8 Conversion (FFmpeg via `subprocess`)

* Use `subprocess.run` to execute the FFmpeg command.
* Include `-protocol_whitelist` to ensure necessary protocols (http, https, etc.) are allowed for input.
* Use appropriate flags: `-acodec mp3`, `-vn` (no video), `-y` (overwrite), `-loglevel error` (or adjust for desired FFmpeg verbosity).
* Implement robust error handling: Check the return code (`check=True`), capture stderr for error messages (`capture_output=True`), handle `CalledProcessError`, `TimeoutExpired`, and `FileNotFoundError`. Set a generous timeout (e.g., 1800+ seconds).

### 4.2. Azure Blob Upload (`azure-storage-blob`)

* **Timeout Critical:** Default timeouts are often insufficient for larger files (e.g., 35MB). Upload failures (`TimeoutError: The write operation timed out`) occurred even with a 30-minute operation timeout set on `upload_blob`.
* **Solution:** Configure timeouts at the client level during `BlobServiceClient` initialization. Set a long `read_timeout` (e.g., 1900+ seconds) and a reasonable `connection_timeout` (e.g., 60 seconds).
    ```python
    # Example Client Initialization
    from azure.storage.blob import BlobServiceClient
    service_client = BlobServiceClient.from_connection_string(
        connection_string,
        connection_timeout=60,
        read_timeout=1900
    )
    # Pass this client to upload/delete functions
    ```
* Use `overwrite=True` in `upload_blob` if re-running tests or if duplicate source files might occur.

### 4.3. SAS URI Generation (`azure-storage-blob`)

* Purpose: Provide temporary, delegated read access to the uploaded blob for the Azure Speech Service.
* Use `generate_blob_sas` function.
* Required Permissions: `BlobSasPermissions(read=True)`.
* Expiry: Set a reasonable expiry time (e.g., `timedelta(hours=2)`) to allow the Speech service sufficient time to access the file.
* Depends on the `AZURE_STORAGE_CONNECTION_STRING` having permissions to generate SAS tokens.

### 4.4. Azure Speech Job Submission (`requests`)

* **Pricing Tier:** The Batch Transcription API endpoint (`/speechtotext/v3.1/transcriptions`) **requires a Standard (S0) pricing tier** for the Azure Speech resource. Using a Free (F0) tier will result in a `400 Bad Request` / `InvalidSubscription` error. Verify the tier in the Azure portal.
* Endpoint: `https://<REGION>.api.cognitive.microsoft.com/speechtotext/v3.1/transcriptions`
* Method: `POST`
* Headers: Requires `Ocp-Apim-Subscription-Key` and `Content-Type: application/json`.
* Payload: JSON body including `contentUrls` (array with the SAS URI), `locale` ("he-IL"), `displayName`, and `properties` (e.g., `wordLevelTimestampsEnabled`).
* Check response status (`response.raise_for_status()`) and ensure the `self` URL (job status URL) is present in the JSON response.

### 4.5. Job Polling (`requests`)

* Poll the `self` URL obtained from the job submission response using GET requests.
* **Authentication:** Each polling request **must** include the `Ocp-Apim-Subscription-Key` header. Accessing the URL without this key (e.g., in a browser) will result in a `401 Unauthorized` error, even if the job is running.
* **Timeout:** Transcription takes time. The polling loop needs a sufficiently long total timeout (`MAX_POLLING_ATTEMPTS * POLLING_INTERVAL_SECONDS`). A duration of **at least 1 hour** is recommended (e.g., 120 attempts * 30 seconds).
* Check the `status` field in the JSON response (`Running`, `Succeeded`, `Failed`).
* Implement delays between polls (`time.sleep`). Handle potential network errors during polling.

### 4.6. Result Retrieval & Parsing (`requests`)

* If job status is `Succeeded`:
    * Get the `files` URL from the `links` section of the job status response.
    * Make a GET request (with auth header) to the `files` URL.
    * Parse the response to find the entry where `kind` is `Transcription`.
    * Extract the `contentUrl` from the `links` section of the transcription file entry. This URL is typically a SAS URL itself and usually doesn't require the API key header for download.
    * Make a GET request to the `contentUrl` to download the transcript JSON content.
* **Parsing Sensitivity:** The structure of the downloaded JSON may vary. The tested job returned text in `combinedRecognizedPhrases[n].lexical`. The parsing logic must target the correct keys.
    * **Recommendation:** Implement parsing for the expected structure (e.g., `combinedRecognizedPhrases`/`lexical`). If parsing fails or the expected keys aren't found, fall back to saving the raw JSON content or logging an error, rather than failing silently.
    ```python
    # Example Corrected Parsing Logic
    phrases = transcript_content.get('combinedRecognizedPhrases', [])
    full_text = " ".join([p.get('lexical', '') for p in phrases if p.get('lexical')])
    ```

### 4.7. Transcript File Saving

* Open the output file in write mode (`'w'`).
* **Crucially, use `encoding='utf-8'`** to correctly handle Hebrew characters.
* Write the extracted `full_text`.

### 4.8. Cleanup

* Use a `finally` block around the main processing logic for each input item to ensure cleanup is attempted even if errors occur.
* **Delete Blob:** Use the `BlobServiceClient` (initialized with timeouts) and the `delete_blob` method. Handle `ResourceNotFoundError` gracefully (if the blob wasn't uploaded or was already deleted).
* **Delete Local MP3:** Use `os.remove()` within a try-except block.
* **(Optional) Delete Speech Job:** The completed Speech job record can also be deleted via a DELETE request to the job's `self` URL (requires auth header). This might be desirable to keep the job list clean in Azure.

## 5. Error Handling & Logging

* Implement `try...except...finally` blocks for each major stage (conversion, upload, SAS, submit, poll, download, parse, save, cleanup).
* Log informative messages at each step. Log errors with details (e.g., FFmpeg stderr, API response bodies, exception messages).
* Utilize the `tenacity` library for automatic retries on transient network errors or specific HTTP status codes (e.g., 429, 5xx) for API calls, as originally planned [cite: Panopto/plan.md].

## 6. Conclusion

The core components have been successfully tested. Key areas requiring attention in the final script are robust timeout handling for blob uploads (client-level timeouts), ensuring the correct Azure Speech tier (S0) is used, reliable transcript JSON parsing, comprehensive error handling, and sufficient polling duration. Incorporating these insights should lead to a functional and robust application.