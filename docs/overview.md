**Project Goal:** Create a single Python script to convert M3U8 streams to text transcripts using Azure services, retrieving results via polling.

**Core Workflow:** Input File -> Convert M3U8 -> Upload MP3 to Azure -> Submit Azure Speech Job -> **Poll for Job Completion** -> Download Transcript -> Save Locally -> Cleanup.

**Key Technologies:**
* Python 3.x
* `requests` library (for Azure Speech REST API)
* `azure-storage-blob` library (for Azure Blob Storage)
* `python-dotenv` library (for configuration)
* `subprocess` module (for M3U8 conversion tool like FFmpeg/VLC)
* `time` module (for polling delay)

---

**Development Plan:**

1.  **Setup:**
    * Initialize Python virtual environment.
    * Install required libraries: `pip install requests azure-storage-blob python-dotenv`
    * Create `.env` file with Azure credentials and configuration [cite: docs/azure_setup.md]:
        * `AZURE_STORAGE_CONNECTION_STRING`
        * `AZURE_STORAGE_INPUT_CONTAINER` (e.g., "input")
        * `AZURE_SPEECH_API_KEY`
        * `AZURE_SPEECH_REGION`
    * Define local paths (e.g., temporary audio folder, final transcript output folder).
    * Ensure FFmpeg or VLC is installed and accessible in the system PATH.

2.  **Script Structure (Single `.py` file):**
    * **Imports:** Import necessary libraries (`requests`, `azure.storage.blob`, `dotenv`, `os`, `subprocess`, `time`, `json`, `logging`).
    * **Configuration:** Load `.env` variables. Set up basic logging.
    * **Helper Functions:** Define functions for clarity:
        * `convert_m3u8_to_mp3(m3u8_url, output_mp3_path)`: Uses `subprocess` to call FFmpeg/VLC. Handles errors.
        * `upload_to_blob(local_file_path, blob_name)`: Uploads file to Azure Blob Storage.
        * `get_blob_sas_uri(blob_name)`: Generates a read-only SAS URI for the blob [cite: docs/plan.md].
        * `delete_blob(blob_name)`: Deletes the blob.
        * `submit_transcription_job(audio_sas_uri, job_name)`: Sends POST request to Azure Speech API `/transcriptions` endpoint. Returns the job status URL (`self` link from response) [cite: docs/azure_speech_webhook.md].
        * `get_job_status(job_url)`: Sends GET request to the job status URL. Returns the job status (e.g., 'Running', 'Succeeded', 'Failed') and the full response JSON [cite: docs/azure_speech_webhook.md].
        * `get_transcript_url(job_files_url)`: Sends GET request to the job's files URL (found in the job status response). Parses the response to find the `contentUrl` for the transcript file [cite: docs/azure_speech_webhook.md].
        * `download_file(url, output_path)`: Downloads content from a URL (like the transcript `contentUrl`).
        * `cleanup_local_file(file_path)`: Deletes local files.
    * **Main Execution Logic:**
        * Read the input file (containing filename/M3U8 pairs).
        * Loop through each pair:
            * Log the start of processing for the current item.
            * Define temporary MP3 path and final transcript path.
            * **Convert:** Call `convert_m3u8_to_mp3`. Handle errors.
            * **Upload:** Call `upload_to_blob`. Define a unique blob name (e.g., using UUID or timestamp). Handle errors.
            * **Get SAS:** Call `get_blob_sas_uri`. Handle errors.
            * **Submit Job:** Call `submit_transcription_job`, passing the SAS URI. Store the returned `job_url`. Handle errors.
            * **Polling Loop:**
                * Start a loop (`while True:`).
                * Call `time.sleep(30)` (or adjust polling interval).
                * Call `get_job_status(job_url)`.
                * Check the returned status:
                    * If 'Succeeded': Break the loop.
                    * If 'Failed': Log error, store failure info, break the loop.
                    * If 'Running' or other intermediate status: Continue loop.
            * **Result Handling:**
                * If status was 'Succeeded':
                    * Extract the `files` URL from the job status response.
                    * Call `get_transcript_url` using the `files` URL.
                    * Call `download_file` using the transcript `contentUrl`.
                    * Parse the downloaded JSON transcript.
                    * Save the formatted transcript locally.
                    * Log success.
                * If status was 'Failed':
                    * Log the failure details extracted from the job status response.
            * **Cleanup:**
                * Call `delete_blob` to remove the MP3 from Azure.
                * Call `cleanup_local_file` to remove the local MP3.
        * Add `try...except...finally` blocks within the loop to handle errors for individual files gracefully and ensure cleanup attempts occur.

3.  **Execution:**
    * Run the script from the command line: `python your_script_name.py input_links.txt`