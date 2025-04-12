// ==UserScript==
// @name         Panopto-Copy-Individual-Stream-M3U8
// @namespace    https://github.com/Panopto-Video-DL
// @description  Adds buttons to copy M3U8 URLs for individual Panopto streams.
// @icon         https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://panopto.com&size=96
// @author       Modified by Gemini based on Panopto-Video-DL
// @version      5.0.1
// @copyright    2021, Panopto-Video-DL; 2025, Modifications by Gemini
// @license      MIT
// @homepage     https://github.com/Panopto-Video-DL/Panopto-Video-DL-browser
// @homepageURL  https://github.com/Panopto-Video-DL/Panopto-Video-DL-browser
// @supportURL   https://github.com/Panopto-Video-DL/Panopto-Video-DL-browser/issues
// @require      https://greasyfork.org/scripts/401626-notify-library/code/Notify%20Library.js
// @match        https://*.panopto.com/Panopto/Pages/Viewer.aspx?*id=*
// @match        https://*.panopto.eu/Panopto/Pages/Viewer.aspx?*id=*
// @match        https://*.panopto.com/Panopto/Pages/Embed.aspx?*id=*
// @match        https://*.panopto.eu/Panopto/Pages/Embed.aspx?*id=*
// @connect      panopto.com // Needed for DeliveryInfo.aspx fetch
// @connect      panopto.eu  // Needed for DeliveryInfo.aspx fetch
// @grant        GM_addStyle
// @grant        GM_setClipboard
// @grant        GM_registerMenuCommand
// @noframes
// ==/UserScript==

/* globals Notify */

(function () {
  'use strict';

  // --- Styles ---
  addStyle(`
    #panopto-stream-copy-container {
      position: fixed;
      bottom: 15px; /* Adjust as needed */
      left: 15px; /* Adjust as needed */
      z-index: 2000; /* Ensure it's above player controls */
      background-color: rgba(45, 52, 54, 0.8); /* Semi-transparent dark background */
      padding: 8px;
      border-radius: 5px;
      display: flex;
      flex-direction: column; /* Stack buttons vertically */
      gap: 5px; /* Space between buttons */
      max-height: 30vh; /* Limit height */
      overflow-y: auto; /* Allow scrolling if many streams */
    }
    #panopto-stream-copy-container button {
      background-color: #dfe6e9;
      color: #2d3436 !important; /* Ensure text is dark */
      border: 1px solid #b2bec3;
      padding: 5px 10px;
      border-radius: 3px;
      cursor: pointer;
      font-size: 12px; /* Smaller font size for buttons */
      text-align: left;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 200px; /* Limit button width */
      margin: 0 !important; /* Override other styles */
    }
    #panopto-stream-copy-container button:hover {
      background-color: #b2bec3;
    }
  `);
  // Style for the Notify library modal (kept for clipboard errors)
  addStyle('#Panopto-Video-DL{position:fixed;top:10%;left:50%;width:70%;padding:2em 3em 1em;background-color:#2d3436;transform:translateX(-50%);z-index:1050}#Panopto-Video-DL *{margin-bottom:10px;color:#fff!important;font-size:18px;}#Panopto-Video-DL > div {margin-top: 1em;}#Panopto-Video-DL ul,#Panopto-Video-DL ol,#Panopto-Video-DL li{margin:0 .5em;padding:0 .5em;list-style:decimal}#Panopto-Video-DL button{margin-left:5px;margin-right:5px;color:#000!important;font-size:16px;}#Panopto-Video-DL p{margin-top:0.5em;}#Panopto-Video-DL input{color:black!important;}#Panopto-Video-DL textarea{width:100%;color:black!important;resize:vertical;white-space:nowrap;}');


  // --- Main Logic ---

  /**
   * Fetches stream info and creates copy buttons for each M3U8 stream.
   */
  async function createStreamCopyButtons() {
    log('Attempting to create stream copy buttons...');
    const url = new URL(location.href);
    const videoId = url.searchParams.get('id');
    if (!videoId) {
      log('Failed to get Lesson ID.', 'error');
      return;
    }
    // Remove container if it exists from a previous run (e.g., SPA navigation)
    document.getElementById('panopto-stream-copy-container')?.remove();
    try {
      const deliveryInfo = await requestDeliveryInfo(videoId);
      const allStreams = getAllM3u8Streams(deliveryInfo); // Ensure this function exists

      if (!allStreams.length) {
        log('No M3U8 stream URLs found in DeliveryInfo.', 'warn');
         // Optionally display a message if container existed or create one to show message
         const buttonContainer = document.getElementById('panopto-stream-copy-container') || document.createElement('div');
         if (!buttonContainer.id) {
             buttonContainer.id = 'panopto-stream-copy-container';
             // Minimal styling if creating just for the message
             buttonContainer.style.position = 'fixed';
             buttonContainer.style.bottom = '15px';
             buttonContainer.style.left = '15px';
             buttonContainer.style.zIndex = '2000';
             buttonContainer.style.backgroundColor = 'rgba(45, 52, 54, 0.8)';
             buttonContainer.style.padding = '8px';
             buttonContainer.style.borderRadius = '5px';
             buttonContainer.style.color = 'white';
             document.body.appendChild(buttonContainer);
         }
         buttonContainer.textContent = "No M3U8 streams found.";
        return;
      }

      log(`Found ${allStreams.length} M3U8 streams.`, allStreams);
      const container = document.createElement('div');
      container.id = 'panopto-stream-copy-container';

      allStreams.forEach((stream, index) => {
        const button = document.createElement('button');
        let buttonText = stream.Name || `Stream ${index + 1}`;
        buttonText = buttonText.replace(/[-_]?(\d{8}T\d+Z)+/g, '')
                               .replace(/-[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}/gi, '')
                               .replace(/[_-]+$/, '')
                               .replace(/_/g, ' ')
                               .trim();
        if (!buttonText) buttonText = `Stream ${index + 1}`;
        button.textContent = `Copy: ${buttonText}`;
        button.title = `Click to copy M3U8 URL:\n${stream.StreamUrl}`;
        button.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          copyToClipboard(stream.StreamUrl, buttonText); // Use the existing copy function
        });
        container.appendChild(button);
      });

      document.body.appendChild(container);
      log('Stream copy buttons created successfully.');

    } catch (error) {
      log(`Error creating stream buttons: ${error.message}`, 'error');
      showErrorNotification(`Error creating buttons: ${error.message}`);
    }
  }

   /**
   * Extracts all streams with M3U8 URLs from DeliveryInfo data.
   */
  function getAllM3u8Streams(deliveryInfo) {
    const streams = [];
    const seenUrls = new Set();
    const processStreamList = (streamList) => {
        if (!streamList || !Array.isArray(streamList)) return;
        streamList.forEach(stream => {
           // Check if StreamUrl exists, is a string, includes .m3u8, and hasn't been added
           if (stream.StreamUrl && typeof stream.StreamUrl === 'string' && stream.StreamUrl.includes('.m3u8') && !seenUrls.has(stream.StreamUrl)) {
               streams.push({ Name: stream.Name || null, StreamUrl: stream.StreamUrl });
               seenUrls.add(stream.StreamUrl);
           }
       });
    };
    processStreamList(deliveryInfo.Delivery?.PodcastStreams);
    processStreamList(deliveryInfo.Delivery?.Streams);
    return streams;
  }


  /**
   * Fetches DeliveryInfo data for a given video ID.
   */
  function requestDeliveryInfo(videoId) {
    return fetch(
      location.origin + '/Panopto/Pages/Viewer/DeliveryInfo.aspx', {
      method: 'POST',
      headers: {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
      },
      body: 'deliveryId=' + videoId + '&isEmbed=true&responseType=json',
    })
      .then(response => {
          if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
          return response.json();
      })
      .then(data => {
        if (data.ErrorCode) throw new Error(data.ErrorMessage || `API Error Code: ${data.ErrorCode}`);
        if (!data.Delivery) throw new Error('Delivery information missing in API response.');
        return data;
      })
      .catch(error => {
        log(error, 'error');
        throw error;
      });
  }

  // --- Utility Functions ---

  function copyToClipboard(text, streamName) {
    const notifySuccess = () => {
       new Notify({ text: `Copied M3U8 for: ${streamName}`, type: 'success', timeout: 2500 }).show();
    };
    if (typeof GM_setClipboard !== 'undefined') {
      GM_setClipboard(text, 'text');
      notifySuccess();
    } else {
      navigator.clipboard.writeText(text).then(() => {
        notifySuccess();
      }).catch(e => {
        log(e, 'error');
        const modal = showModal('<h3>Clipboard error</h3> <p>Copy the M3U8 URL manually:</p><textarea type="text" value="" rows="3" onclick="this.select();"></textarea><p style="text-align:center;"><button onclick="this.parentElement.parentElement.remove();">Close</button></p>');
        modal.querySelector('textarea').value = text;
      });
    }
  }

  function showErrorNotification(message) {
    new Notify({ text: message, type: 'error', timeout: null }).show();
  }

 function showModal(html) {
     const existingModal = document.querySelector('#Panopto-Video-DL');
     if (existingModal) {
         existingModal.innerHTML = html; // Replace content
         return existingModal;
     } else {
         // Create and append new modal if it doesn't exist
         const newModal = document.createElement('div');
         newModal.id = 'Panopto-Video-DL'; // Use the consistent ID for styling
         newModal.innerHTML = html;
         document.body.appendChild(newModal);
         return newModal;
     }
 }

  function addStyle(CSS) {
    if (typeof GM_addStyle != 'undefined') {
      GM_addStyle(CSS);
    } else {
      const style = document.createElement('style');
      style.innerText = CSS;
      document.head.appendChild(style);
    }
  }

  function log(message, level = 'log') {
    const prefix = '%c Panopto-Copy-Individual-Stream ->';
    const style = 'color:green;font-size:14px;';
    switch (level) {
      case 'warn': console.warn(prefix, style, message); break;
      case 'error': console.error(prefix, style, message); break;
      case 'log': default: console.log(prefix, style, message); break;
    }
  }

  // --- Initialization ---
  let initTimeout = null;
  let observer = null; // Define observer variable

  function initializeScript() {
       // Check if already initialized
       if (document.getElementById('panopto-stream-copy-container')) {
            log("Script UI already initialized.");
            return;
       }

       if(observer) observer.disconnect(); // Disconnect previous observer if any

       observer = new MutationObserver((mutationsList, obs) => {
           const playerReadyElement = document.querySelector('#viewercontainer');
           if (playerReadyElement) {
               log("Player UI element (#viewercontainer) detected. Creating buttons.");
               clearTimeout(initTimeout);
               obs.disconnect(); // Stop observing once done
               createStreamCopyButtons(); // Create buttons
           }
       });

       // Fallback timeout
       initTimeout = setTimeout(() => {
           log("Timeout waiting for player UI (#viewercontainer). Attempting button creation anyway.");
           if(observer) observer.disconnect();
           createStreamCopyButtons();
       }, 7000);

       // Start observing
       log("Starting observer to detect player UI...");
       observer.observe(document.body, { childList: true, subtree: true });
  }

  // Run the initialization logic
  initializeScript();

})(); // End of script IIFE