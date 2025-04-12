# M3U8 to Hebrew Transcript Pipeline

## 1. Overview

This Python application automates the process of converting video/audio streams provided as M3U8 URLs into Hebrew text transcripts. It leverages FFmpeg for local media conversion and utilizes Azure AI Speech (Batch Transcription API) and Azure Blob Storage for cloud-based processing and storage. The script processes a list of input URLs from a file, manages temporary files, polls for transcription completion, retrieves results, and performs cleanup.

## 2. Features

* **Batch Processing:** Handles multiple M3U8 URLs listed in an input file.
* **M3U8 Conversion:** Uses FFmpeg to convert M3U8 streams to temporary MP3 files.
* **Azure Integration:**
    * Uploads MP3 files to Azure Blob Storage.
    * Submits transcription jobs to Azure AI Speech Batch Transcription API (v3.2).
    * Requires a **Standard (S0) pricing tier** for the Azure Speech resource.
* **Polling:** Checks Azure job status periodically until completion or timeout.
* **Result Parsing:** Extracts Hebrew text from the transcription result JSON.
* **Local Output:** Saves final transcripts as `.txt` files locally.
* **Cleanup:** Automatically deletes temporary local MP3 files and blobs from Azure Storage after processing each item.
* **Configuration:** Uses a `.env` file for credentials and settings.
* **Logging:** Outputs progress and errors to both the console and a log file (`transcript_processing.log`).
* **Error Handling:** Includes error handling for various stages and attempts to continue processing subsequent items in the input file if one fails.
* **Retries (Optional):** Includes optional retry logic for API calls using the `tenacity` library if installed.

## 3. Prerequisites

* **Python:** Python 3.8 or higher recommended.
* **FFmpeg:** Must be installed on the system running the script and its executable must be accessible via the system's `PATH` environment variable. Download from [https://ffmpeg.org/](https://ffmpeg.org/).
* **Azure Account:** An active Azure subscription.
* **Azure Resources:**
    * **Azure Storage Account:** A general-purpose storage account.
    * **Azure Blob Storage Container:** A container within the storage account (e.g., named "mp3").
    * **Azure AI Speech Service Resource:**
        * Must be created with the **Standard (S0) pricing tier**. The Free (F0) tier is **not sufficient** for the Batch Transcription API used by this script.
        * Note the API Key and Region for this resource.

## 4. Setup

1.  **Clone the Repository (Example):**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```
2.  **Create Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/macOS
    # OR
    .\.venv\Scripts\activate  # Windows
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Ensure `requirements.txt` contains at least `requests`, `azure-storage-blob`, `python-dotenv`, and optionally `tenacity`)*

## 5. Configuration (`.env` File)

Create a file named `.env` in the root directory of the project. Add the following environment variables:

```dotenv
# --- Required Azure Credentials ---
# Full connection string for your Azure Storage Account
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=YOUR_ACCOUNT_NAME;AccountKey=YOUR_ACCOUNT_KEY;EndpointSuffix=core.windows.net"

# Name of the container in your Storage Account for temporary MP3 uploads
AZURE_STORAGE_INPUT_CONTAINER="mp3" # Or your chosen container name

# API Key for your Azure AI Speech Service resource (must be S0 tier)
AZURE_SPEECH_API_KEY="YOUR_S0_SPEECH_API_KEY"

# Region of your Azure AI Speech Service resource (e.g., eastus)
AZURE_SPEECH_REGION="eastus"


# --- Optional Settings (Defaults Shown) ---
# Directory for temporary local MP3 files
# LOCAL_TEMP_AUDIO_DIR="./temp_audio/"

# Directory for final transcript output files
# LOCAL_TRANSCRIPT_OUTPUT_DIR="./transcripts/"

# Timeout for establishing connection to Azure Storage (seconds)
# CLIENT_CONNECTION_TIMEOUT_SECONDS=60

# Timeout for waiting between data packets during Azure Storage operations (seconds)
# IMPORTANT: Increase if uploads time out (e.g., for large files or slower networks)
# CLIENT_READ_TIMEOUT_SECONDS=1900

# Interval between polling attempts for job status (seconds)
# POLLING_INTERVAL_SECONDS=30

# Maximum number of polling attempts before timing out
# Adjust based on expected job duration (MAX_POLLING_ATTEMPTS * POLLING_INTERVAL_SECONDS = total seconds)
# MAX_POLLING_ATTEMPTS=120 # (Default = 120 * 30s = 1 hour)

# Timeout for the FFmpeg conversion process (seconds)
# FFMPEG_TIMEOUT_SECONDS=1800 # (Default = 30 minutes)

# Version of the Azure Speech API to use (confirm this matches the service)
# API_VERSION="v3.2"
```

**Security Note:** The `.env` file contains sensitive credentials. Ensure it is added to your `.gitignore` file and never committed to version control. Regenerate keys immediately if they are accidentally exposed.

## 6. Input File Format (`main_application.py`)

The main script requires an input text file specified as a command-line argument. This file must contain pairs of lines in the following format:

```
<output_transcript_base_filename_1>
<m3u8_url_1>
<output_transcript_base_filename_2>
<m3u8_url_2>
...
```

* `<output_transcript_base_filename_n>`: The desired base name for the output `.txt` transcript file (do not include the `.txt` extension).
* `<m3u8_url_n>`: The full URL to the M3U8 stream.

**Example (`input.txt`):**
```
lecture_01_probability
[https://d2hpwsdp0ihr0w.cloudfront.net/.../master.m3u8](https://d2hpwsdp0ihr0w.cloudfront.net/.../master.m3u8)
meeting_notes_april_9
[https://example.com/stream/meeting.m3u8](https://example.com/stream/meeting.m3u8)
```

## 7. Usage (`main_application.py`)

Run the main script from your terminal within the activated virtual environment:

```bash
python main_application.py <path/to/your/input_file.txt>
```

Replace `<path/to/your/input_file.txt>` with the actual path to your input file.

## 8. Workflow (`main_application.py`)

For each pair in the input file, the script performs the following steps:

1.  **Convert:** Calls FFmpeg to convert the M3U8 URL to a temporary local MP3 file.
2.  **Upload:** Uploads the MP3 file to the specified Azure Blob Storage container.
3.  **Generate SAS:** Creates a temporary Read-only SAS URI for the uploaded blob.
4.  **Submit Job:** Sends a request to the Azure AI Speech Batch Transcription API with the SAS URI.
5.  **Poll Status:** Periodically checks the Azure job status using the Job URL until 'Succeeded' or 'Failed' or timeout.
6.  **Retrieve Results:** If the job succeeded, downloads the transcript result file (JSON format).
7.  **Parse & Save:** Parses the JSON to extract the Hebrew text and saves it to a local `.txt` file.
8.  **Cleanup:** Deletes the temporary local MP3 file and the corresponding blob from Azure Storage.

## 9. Retrieving Transcripts from Failed/Interrupted Jobs (`collect_transcript.py`)

If the main script (`main_application.py`) fails or is interrupted after submitting a job to Azure (e.g., due to network issues during polling), the transcription might still complete successfully on Azure's side. The `collect_transcript.py` script allows you to manually retrieve the transcript for a specific job ID.

**How it Works:**

1.  **Reads `.env`:** Uses the same Azure credentials and settings from your `.env` file.
2.  **Takes Job Info:** Requires you to manually edit the script to input the `JOB_NAME` (for the output filename) and the `JOB_ID` (found in the logs of the original run, e.g., `transcript_processing.log`).
3.  **Polls Azure:** Connects to Azure and polls the status of the specific `JOB_ID`.
4.  **Downloads & Saves:** If the job status is 'Succeeded', it downloads the transcript content and saves it as `<JOB_NAME>.txt` in your configured `LOCAL_TRANSCRIPT_OUTPUT_DIR`.

**Usage (`collect_transcript.py`):**

1.  **Find Job ID:** Locate the `JOB_ID` for the failed/interrupted job in the `transcript_processing.log` file or the console output of the original run. Look for lines like `Job submitted successfully. Job URL: .../transcriptions/<JOB_ID>` or `Polling job status.../transcriptions/<JOB_ID>`.
2.  **Find Job Name:** Recall the base filename associated with the M3U8 URL for that job from your original `input.txt`.
3.  **Edit Script:** Open `collect_transcript.py` in a text editor. Locate the section `--- User Input ---` near the top and replace the placeholder values for `JOB_NAME` and `JOB_ID` with the actual values you found.
    ```python
    # --- User Input ---
    # TODO: Replace these values with the actual Job Name and Job ID you want to retrieve
    JOB_NAME = "your_job_base_filename" # e.g., "lecture_01_probability"
    JOB_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" # The ID from the logs
    # --- End User Input ---
    ```
4.  **Run Script:** Execute the script from your terminal within the activated virtual environment:
    ```bash
    python collect_transcript.py
    ```
5.  **Check Output:** If the job had succeeded on Azure, the script will download the transcript and save it to the output directory (e.g., `./transcripts/your_job_base_filename.txt`). Check the console output for success or error messages.

## 10. Output

* **Transcripts:** Successfully generated transcripts are saved as `.txt` files in the directory specified by `LOCAL_TRANSCRIPT_OUTPUT_DIR` (default: `./transcripts/`). Files are named according to the base names provided in the input file (for `main_application.py`) or the `JOB_NAME` specified in `collect_transcript.py`.
* **Logs:** Detailed progress and error information are printed to the console and saved to the `transcript_processing.log` file in the script's root directory (for `main_application.py`). `collect_transcript.py` primarily logs to the console.

## 11. Error Handling & Logging

* The scripts use `try...except...finally` blocks to handle errors gracefully.
* `main_application.py`: If an error occurs while processing one item, it logs the error and attempts to continue with the next item. Check `transcript_processing.log` for details.
* `collect_transcript.py`: Logs errors primarily to the console.
* If the `tenacity` library is installed, API calls will be automatically retried on transient network errors or specific server-side issues.

## 12. Troubleshooting Common Issues

* **`FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'`:** FFmpeg is not installed or not in the system's PATH. Verify installation and PATH configuration.
* **`400 Client Error: Bad Request ... InvalidSubscription`:** The Azure Speech Service resource associated with the provided API key is not on the **Standard (S0)** pricing tier. Change the tier to S0 in the Azure portal or create a new S0 resource and update the `.env` file.
* **Upload Timeout Errors (`TimeoutError: The write operation timed out`)**: The upload took longer than the configured timeout. Increase `CLIENT_READ_TIMEOUT_SECONDS` in the `.env` file. Check network stability and speed.
* **`404 Client Error: Not Found` during Polling:**
    * For `main_application.py`: Could indicate a temporary Azure issue or an incorrect job URL construction.
    * For `collect_transcript.py`: Double-check the `JOB_ID`, `AZURE_SPEECH_REGION`, and `API_VERSION` (in `.env`) are correct and match the original job submission. Ensure the job wasn't deleted.
* **Authentication Errors (Storage or Speech):** Double-check that the `AZURE_STORAGE_CONNECTION_STRING` and `AZURE_SPEECH_API_KEY` in the `.env` file are correct and correspond to active resources with the necessary permissions/tier. Regenerate keys if unsure.
* **Transcription Parsing Errors:** If a script saves a `.raw.json` file instead of a `.txt` file, it means the structure of the JSON returned by Azure didn't match the expected parsing logic. Inspect the raw JSON and adjust the parsing logic in the `save_transcript_to_file` function if necessary.