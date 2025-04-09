# Azure Setup Guide for M3U8 Transcription Pipeline

## 1. Introduction

This guide walks you through setting up the required Microsoft Azure cloud resources needed to run the M3U8-to-Hebrew-Transcript Python application. You will need an active Azure subscription to proceed.

We will create:

1.  An **Azure Storage Account** to temporarily store converted MP3 files.
2.  A **Blob Storage Container** within that account.
3.  An **Azure AI Speech Service** resource for performing the transcription.

We will also retrieve the necessary credentials (keys, connection strings, region names) required for the application's `.env` configuration file.

## 2. Step 1: Create Azure Storage Account

This account will hold the temporary MP3 audio files before they are sent for transcription.

1.  **Log in** to the [Azure Portal](https://portal.azure.com/).
2.  In the top search bar, search for **"Storage accounts"** and select it from the services list.
3.  Click the **"+ Create"** button.
4.  Fill in the **Basics** tab:
    * **Subscription:** Choose your active Azure subscription.
    * **Resource group:** Select an existing resource group or click "Create new" to make one (e.g., `rg-transcription-pipeline`). Resource groups help organize Azure resources.
    * **Storage account name:** Enter a **globally unique** name (lowercase letters and numbers only, e.g., `youruniquestoragename` followed by some numbers). Remember this name.
    * **Region:** Choose an Azure region (e.g., `East US`). It's often beneficial to choose the same region where you plan to create the Speech service resource later.
    * **Performance:** Standard (recommended).
    * **Redundancy:** Geo-redundant storage (GRS) or Locally-redundant storage (LRS) are common choices (LRS is usually cheaper).
5.  You can leave the settings on the other tabs (Advanced, Networking, etc.) as default for now unless you have specific requirements.
6.  Click **"Review"** and then **"Create"**.
7.  Wait for the deployment to complete.

## 3. Step 2: Create Blob Storage Container

Within the storage account, we need a container to hold the blobs (files).

1.  Once the storage account deployment is complete, click **"Go to resource"** or find your new storage account via the Azure portal search.
2.  In the storage account's left-hand navigation pane, under **"Data storage"**, click on **"Containers"**.
3.  Click the **"+ Container"** button near the top.
4.  Enter the **Name:** `mp3` (This matches the default expected by the application script, `AZURE_STORAGE_INPUT_CONTAINER`). You can change this, but you'll need to update the `.env` file accordingly.
5.  Set **Public access level:** Private (no anonymous access) (recommended).
6.  Click **"Create"**.

## 4. Step 3: Get Storage Account Connection String

The application needs credentials to access this storage account.

1.  In your storage account's left-hand navigation pane, under **"Security + networking"**, click on **"Access keys"**.
2.  You will see two keys listed (key1 and key2). Click the **"Show"** button next to one of them (e.g., key1).
3.  Find the **"Connection string"** field associated with that key. Click the copy icon next to it to copy the entire string.
4.  **Save this connection string securely** (e.g., in a temporary text file). You will need it for the `.env` file later. **Treat this like a password.**

## 5. Step 4: Create Azure AI Speech Service

This service performs the actual speech-to-text transcription.

1.  In the Azure Portal's top search bar, search for **"Speech services"** and select it.
2.  Click the **"+ Create"** button.
3.  Fill in the **Basics** tab:
    * **Subscription:** Choose your active Azure subscription.
    * **Resource group:** Select the same resource group you used for the storage account.
    * **Region:** Choose an Azure region (e.g., `East US`). **It's strongly recommended to use the same region as your Storage Account** to minimize latency and potential data transfer costs. Make sure this matches the region you intend to use in your `.env` file.
    * **Name:** Enter a unique name for your speech service (e.g., `yourunique-speech-service`).
    * **Pricing tier:** This is **CRITICAL**. Select **Standard S0**. **Do NOT use the Free F0 tier**, as testing showed it results in `InvalidSubscription` errors when using the Batch Transcription API required by this application. The S0 tier is paid and usage costs will apply.
4.  Review the network, identity, and tags tabs if needed, or leave defaults.
5.  Click **"Review + create"** and then **"Create"**.
6.  Wait for the deployment to complete.

## 6. Step 5: Get Speech Service Key and Region

The application needs credentials for the Speech service.

1.  Once the Speech service deployment is complete, click **"Go to resource"** or find it via the portal search.
2.  In the speech service's left-hand navigation pane, under **"Resource Management"**, click on **"Keys and Endpoint"**.
3.  You will see two keys (KEY 1 and KEY 2) and the Location/Region.
4.  Copy **KEY 1**. **Save this key securely.** You will need it for the `AZURE_SPEECH_API_KEY` in the `.env` file. **Treat this like a password.**
5.  Note down the **Location** value (e.g., `eastus`). You will need this exact value for the `AZURE_SPEECH_REGION` in the `.env` file.

## 7. Step 6: Configure `.env` File

Now, create the `.env` file in your local project directory and paste the credentials you copied:

```dotenv
# Azure Storage Account
AZURE_STORAGE_CONNECTION_STRING="PASTE_YOUR_COPIED_CONNECTION_STRING_HERE"
AZURE_STORAGE_INPUT_CONTAINER="mp3" # Or the name you chose in Step 2

# Azure Speech Service (Must be Standard S0 tier!)
AZURE_SPEECH_API_KEY="PASTE_YOUR_COPIED_SPEECH_KEY_1_HERE"
AZURE_SPEECH_REGION="PASTE_THE_SPEECH_SERVICE_LOCATION_HERE" # e.g., eastus

# Add any optional overrides here if needed (timeouts, polling intervals, etc.)
# CLIENT_READ_TIMEOUT_SECONDS=1900
# MAX_POLLING_ATTEMPTS=120
# POLLING_INTERVAL_SECONDS=30