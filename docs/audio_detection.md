# Developer Guide: Implementing Audio Stream Detection in Panopto via M3U8 Manifest Parsing

## 1. Objective

To automatically identify which HLS (HTTP Live Streaming) stream URL provided by Panopto corresponds to the video feed containing audible content (e.g., speaker audio) by parsing the associated M3U8 manifest file. This guide details the recommended implementation based on analyzing the `CODECS` attribute within the manifest[cite: 135].

## 2. Background

Panopto sessions can contain multiple HLS streams (e.g., primary speaker video, secondary screen share). Often, only the primary stream contains audio[cite: 2]. Relying on Panopto's internal metadata (`DeliveryInfo.aspx`) or heuristics like resolution/bitrate has proven unreliable[cite: 16, 102, 133]. Direct audio analysis faces feasibility issues (CORS) and performance drawbacks[cite: 71, 72, 134]. Parsing the standardized M3U8 manifest offers the most robust, standards-based solution[cite: 35, 36, 115, 137].

## 3. Prerequisites

* **Environment:** A client-side JavaScript execution environment (e.g., a browser extension, Tampermonkey script) capable of making HTTP requests and running JavaScript.
* **M3U8 Parser Library:** A JavaScript library capable of parsing HLS M3U8 manifest files. The `videojs/m3u8-parser` is recommended due to its specific focus and features[cite: 34, 120].
    * **GitHub:** [https://github.com/videojs/m3u8-parser](https://github.com/videojs/m3u8-parser) [cite: 142]
    * **Integration:** Include the library in your project (e.g., via `<script>`, module import, or Tampermonkey's `@require`).

## 4. Implementation Steps

### Step 4.1: Obtain Candidate M3U8 Stream URLs

* Fetch the relevant session data from Panopto's internal `DeliveryInfo.aspx` endpoint (or equivalent mechanism providing stream URLs)[cite: 8].
* Extract all potential HLS stream URLs (ending in `.m3u8`) from the response (e.g., from `Delivery.Streams` or `Delivery.PodcastStreams`)[cite: 12].

### Step 4.2: Fetch M3U8 Manifest Content

* For **each** candidate M3U8 URL obtained in Step 4.1:
    * Asynchronously fetch the content of the M3U8 manifest file[cite: 23].
    * **Recommendation:** Use `GM_xmlhttpRequest` if implementing within Tampermonkey for better cross-origin request handling, or standard `Workspace` otherwise[cite: 29, 122].
    * Handle potential network errors gracefully (e.g., 404 Not Found, timeouts).

### Step 4.3: Parse the M3U8 Manifest

* For each successfully fetched manifest content:
    * Instantiate your chosen M3U8 parser (e.g., `m3u8Parser.Parser()`)[cite: 31, 123].
    * Pass the manifest text content to the parser (e.g., `parser.push(manifestText)`)[cite: 31, 123].
    * Signal the end of input if required by the library (e.g., `parser.end()`).
    * Access the parsed manifest object (e.g., `parser.manifest`)[cite: 31, 123].
    * Implement robust error handling for parsing failures (invalid manifest format).

### Step 4.4: Analyze CODECS Attribute

* Examine the parsed manifest structure, specifically looking for variant stream definitions, typically found under tags like `#EXT-X-STREAM-INF`[cite: 25, 123].
* For each variant stream listed in the manifest:
    * Access its `attributes` property.
    * Check for the presence of a `CODECS` attribute[cite: 26, 124].
    * If the `CODECS` attribute exists, inspect its string value.
    * **Determine Audio Presence:** Search the `CODECS` string for known audio codec identifiers[cite: 124]. Common identifiers include:
        * `mp4a.40.2` (AAC-LC) [cite: 27]
        * `mp4a.40.5` (HE-AAC)
        * `mp4a.40.29` (HE-AAC v2)
        * `ac-3` (Dolby Digital)
        * `ec-3` (Enhanced AC-3)
        * (Consult HLS specifications or common practice for a more exhaustive list if needed).
    * **Flag Stream:** If an audio codec identifier is found within the `CODECS` string for *any* variant stream defined in that manifest, consider the corresponding M3U8 URL (from Step 4.1) as representing an **audio-bearing stream**[cite: 125].

### Step 4.5: Filter and Utilize Results

* Maintain a list or mapping associating the original M3U8 URLs with the analysis result (contains audio: true/false).
* Based on the analysis, filter the initial list of stream URLs to retain only those identified as containing audio[cite: 126].
* Use this filtered list for subsequent actions (e.g., displaying download links, initiating playback)[cite: 127].
* **Handling Multiple Audio Streams:** If the analysis identifies multiple audio-bearing streams (less common for typical Panopto setups but possible), implement a strategy to select the desired one[cite: 128]:
    * Prioritize based on heuristics (e.g., resolution - higher might indicate primary camera).
    * Present the options to the user for manual selection.

## 5. Code Example Snippet (Conceptual - using `videojs/m3u8-parser`)

```javascript
// --- Assuming 'm3u8Parser' is imported/required ---
// --- Assuming 'streamUrls' is an array of M3U8 URLs ---
// --- Assuming 'fetchManifestContent' is an async function returning manifest text ---

async function findAudioStreams(streamUrls) {
    const audioStreams = [];

    for (const url of streamUrls) {
        try {
            const manifestText = await fetchManifestContent(url); // Use GM_xmlhttpRequest or fetch

            const parser = new m3u8Parser.Parser();
            parser.push(manifestText);
            parser.end();

            const parsedManifest = parser.manifest;

            // Check playlists (variant streams)
            if (parsedManifest.playlists && parsedManifest.playlists.length > 0) {
                for (const playlist of parsedManifest.playlists) {
                    if (playlist.attributes && playlist.attributes.CODECS) {
                        const codecs = playlist.attributes.CODECS.toLowerCase();
                        // Add more audio codec checks if needed
                        if (codecs.includes('mp4a.') || codecs.includes('ac-3') || codecs.includes('ec-3')) {
                            audioStreams.push(url);
                            break; // Found audio in this manifest, no need to check other variants within it
                        }
                    }
                }
            }
            // Optional: Check #EXT-X-MEDIA TYPE=AUDIO tags as well if necessary,
            // though CODECS in #EXT-X-STREAM-INF is often sufficient.

        } catch (error) {
            console.error(`Error processing manifest ${url}:`, error);
            // Handle fetch or parse errors appropriately
        }
    }
    return audioStreams;
}

// --- Example Usage ---
// findAudioStreams(listOfPanoptoStreamUrls)
//    .then(streamsWithAudio => {
//        console.log('Detected audio streams:', streamsWithAudio);
//        // Use the 'streamsWithAudio' array
//    });