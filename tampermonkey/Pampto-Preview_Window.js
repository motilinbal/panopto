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

  // --- Inject Preview Helper and hls.js into Page Context ---
  let previewHelperInjected = false;
  function injectPreviewHelper() {
    if (previewHelperInjected) return;
    previewHelperInjected = true;
    // Inject hls.js
    if (!document.getElementById('panopto-hlsjs-script')) {
      const hlsScript = document.createElement('script');
      hlsScript.id = 'panopto-hlsjs-script';
      hlsScript.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js';
      document.head.appendChild(hlsScript);
    }
    // Inject preview helper
    if (!document.getElementById('panopto-preview-helper-script')) {
      const helperScript = document.createElement('script');
      helperScript.id = 'panopto-preview-helper-script';
      helperScript.textContent = `
        (function() {
          if (window.PanoptoShowPreview) return;
          let hlsPreviewInstance = null;
          let lastPreviewUrl = null;
          window.PanoptoShowPreview = function(m3u8Url) {
            let preview = document.getElementById('panopto-stream-preview');
            if (!preview) {
              preview = document.createElement('div');
              preview.id = 'panopto-stream-preview';
              const copyContainer = document.getElementById('panopto-stream-copy-container');
              if (copyContainer && copyContainer.parentNode) {
                copyContainer.parentNode.appendChild(preview);
              } else {
                document.body.appendChild(preview);
              }
            }
            preview.innerHTML = '';
            const video = document.createElement('video');
            video.id = 'panopto-stream-preview-video';
            video.setAttribute('playsinline', '');
            video.setAttribute('autoplay', '');
            video.setAttribute('muted', '');
            video.setAttribute('controls', '');
            video.style.background = '#000';
            video.style.display = 'block';
            video.style.outline = 'none';
            video.style.objectFit = 'contain';
            if (hlsPreviewInstance) {
              try { hlsPreviewInstance.destroy(); } catch(e){}
              hlsPreviewInstance = null;
            }
            if (lastPreviewUrl === m3u8Url) {
              video.load();
            }
            lastPreviewUrl = m3u8Url;
            function playVideo() {
              video.play().catch(()=>{});
            }
            if (video.canPlayType('application/vnd.apple.mpegurl')) {
              video.src = m3u8Url;
              preview.appendChild(video);
              playVideo();
            } else {
              // Wait for hls.js to be available
              function tryHls() {
                if (window.Hls) {
                  hlsPreviewInstance = new window.Hls();
                  hlsPreviewInstance.loadSource(m3u8Url);
                  hlsPreviewInstance.attachMedia(video);
                  hlsPreviewInstance.on(window.Hls.Events.ERROR, function (event, data) {
                    video.poster = '';
                    video.controls = false;
                    video.style.background = '#000';
                    video.src = '';
                    preview.innerHTML = '<div style="color:#fff;padding:10px;">Failed to load stream preview.</div>';
                  });
                  preview.appendChild(video);
                  playVideo();
                } else {
                  setTimeout(tryHls, 100);
                }
              }
              tryHls();
            }
          };
        })();
      `;
      document.body.appendChild(helperScript);
    }
  }
  'use strict';

  // --- Styles ---
  addStyle(`
    #panopto-stream-copy-container {
      position: fixed;
      bottom: 15px;
      left: 15px;
      z-index: 2000;
      background-color: rgba(45, 52, 54, 0.8);
      padding: 8px;
      border-radius: 5px;
      display: flex;
      flex-direction: column;
      gap: 5px;
      max-height: 30vh;
      overflow-y: auto;
    }
    #panopto-stream-copy-container button {
      background-color: #dfe6e9;
      color: #2d3436 !important;
      border: 1px solid #b2bec3;
      padding: 5px 10px;
      border-radius: 3px;
      cursor: pointer;
      font-size: 12px;
      text-align: left;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 200px;
      margin: 0 !important;
    }
    #panopto-stream-copy-container button:hover {
      background-color: #b2bec3;
    }
    #panopto-stream-preview {
      position: fixed;
      bottom: 15px;
      left: 240px; /* To the right of the copy container */
      z-index: 2001;
      background: rgba(30, 30, 30, 0.95);
      border-radius: 6px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.25);
      padding: 8px 8px 4px 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    #panopto-stream-preview-video {
      width: 320px;
      height: 180px;
      background: #000;
      border-radius: 4px;
      outline: none;
    }
    /* Hide seek bar, volume, and fullscreen controls, keep only play/pause */
    #panopto-stream-preview-video::-webkit-media-controls-timeline,
    #panopto-stream-preview-video::-webkit-media-controls-volume-slider,
    #panopto-stream-preview-video::-webkit-media-controls-mute-button,
    #panopto-stream-preview-video::-webkit-media-controls-fullscreen-button,
    #panopto-stream-preview-video::-webkit-media-controls-current-time-display,
    #panopto-stream-preview-video::-webkit-media-controls-time-remaining-display,
    #panopto-stream-preview-video::-webkit-media-controls-seek-back-button,
    #panopto-stream-preview-video::-webkit-media-controls-seek-forward-button {
      display: none !important;
    }
    /* For Firefox, hide controls except play/pause */
    #panopto-stream-preview-video::-moz-media-controls-enclosure {
      overflow: hidden;
    }
    #panopto-stream-preview-video::-moz-media-controls-timeline,
    #panopto-stream-preview-video::-moz-media-controls-volume-control,
    #panopto-stream-preview-video::-moz-media-controls-mute-button,
    #panopto-stream-preview-video::-moz-media-controls-fullscreen-button {
      display: none !important;
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
      
      
         // --- Streaming Preview Logic ---
         let hlsPreviewInstance = null;
         let lastPreviewUrl = null;
         let hlsScriptLoading = false;
         let hlsScriptLoaded = false;
         let hlsScriptLoadCallbacks = [];
      
         function injectHlsScript(callback) {
           if (hlsScriptLoaded) {
             callback();
             return;
           }
           hlsScriptLoadCallbacks.push(callback);
           if (hlsScriptLoading) return;
           hlsScriptLoading = true;
           const script = document.createElement('script');
           script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js';
           script.onload = function() {
             hlsScriptLoaded = true;
             hlsScriptLoading = false;
             while (hlsScriptLoadCallbacks.length) {
               const cb = hlsScriptLoadCallbacks.shift();
               if (typeof cb === 'function') cb();
             }
           };
           script.onerror = function() {
             hlsScriptLoading = false;
             hlsScriptLoaded = false;
             while (hlsScriptLoadCallbacks.length) {
               const cb = hlsScriptLoadCallbacks.shift();
               if (typeof cb === 'function') cb(new Error('Failed to load hls.js'));
             }
           };
           // Inject into page context for Tampermonkey compatibility
           (document.head || document.body).appendChild(script);
         }
      
         function getHlsConstructor() {
           // Try unsafeWindow (Tampermonkey), then window
           if (typeof unsafeWindow !== 'undefined' && unsafeWindow.Hls) return unsafeWindow.Hls;
           if (window.Hls) return window.Hls;
           return null;
         }
      
         function showStreamPreview(m3u8Url) {
           // Remove existing preview if present
           let preview = document.getElementById('panopto-stream-preview');
           if (!preview) {
             preview = document.createElement('div');
             preview.id = 'panopto-stream-preview';
             // Insert after the copy container if possible, else append to body
             const copyContainer = document.getElementById('panopto-stream-copy-container');
             if (copyContainer && copyContainer.parentNode) {
               copyContainer.parentNode.appendChild(preview);
             } else {
               document.body.appendChild(preview);
             }
           }
           // Clear preview content
           preview.innerHTML = '';
           // Create video element
           const video = document.createElement('video');
           video.id = 'panopto-stream-preview-video';
           video.setAttribute('playsinline', '');
           video.setAttribute('autoplay', '');
           video.setAttribute('muted', '');
           video.setAttribute('controls', '');
           video.style.background = '#000';
           video.style.display = 'block';
           video.style.outline = 'none';
           video.style.objectFit = 'contain';
           // Only show pause/play, hide seek/volume/fullscreen via CSS (already injected)
           // Clean up previous hls.js instance if any
           if (hlsPreviewInstance) {
             try { hlsPreviewInstance.destroy(); } catch(e){}
             hlsPreviewInstance = null;
           }
           // If same URL as last, just reload
           if (lastPreviewUrl === m3u8Url) {
             video.load();
           }
           lastPreviewUrl = m3u8Url;
           // HLS support check
           if (video.canPlayType('application/vnd.apple.mpegurl')) {
             video.src = m3u8Url;
             video.play().catch(()=>{});
             preview.appendChild(video);
           } else {
             // Dynamically load hls.js into page context
             injectHlsScript(function(err) {
               if (err) {
                 preview.innerHTML = '<div style="color:#fff;padding:10px;">Failed to load hls.js for preview.</div>';
                 return;
               }
               const HlsCtor = getHlsConstructor();
               if (!HlsCtor) {
                 preview.innerHTML = '<div style="color:#fff;padding:10px;">hls.js is not available in this context.</div>';
                 return;
               }
               hlsPreviewInstance = new HlsCtor();
               hlsPreviewInstance.loadSource(m3u8Url);
               hlsPreviewInstance.attachMedia(video);
               hlsPreviewInstance.on(HlsCtor.Events.ERROR, function (event, data) {
                 video.poster = '';
                 video.controls = false;
                 video.style.background = '#000';
                 video.src = '';
                 preview.innerHTML = '<div style="color:#fff;padding:10px;">Failed to load stream preview.</div>';
               });
               preview.appendChild(video);
               video.play().catch(()=>{});
             });
           }
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
          injectPreviewHelper(); // Ensure helper is injected
          // Use unsafeWindow if available, else window
          const previewFn = (typeof unsafeWindow !== 'undefined' ? unsafeWindow.PanoptoShowPreview : window.PanoptoShowPreview);
          if (typeof previewFn === 'function') {
            previewFn(stream.StreamUrl);
          }
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

  // --- Streaming Preview Logic ---
  let hlsPreviewInstance = null;
  let lastPreviewUrl = null;

  function showStreamPreview(m3u8Url) {
    // Remove existing preview if present
    let preview = document.getElementById('panopto-stream-preview');
    if (!preview) {
      preview = document.createElement('div');
      preview.id = 'panopto-stream-preview';
      // Insert after the copy container if possible, else append to body
      const copyContainer = document.getElementById('panopto-stream-copy-container');
      if (copyContainer && copyContainer.parentNode) {
        copyContainer.parentNode.appendChild(preview);
      } else {
        document.body.appendChild(preview);
      }
    }
    // Clear preview content
    preview.innerHTML = '';
    // Create video element
    const video = document.createElement('video');
    video.id = 'panopto-stream-preview-video';
    video.setAttribute('playsinline', '');
    video.setAttribute('autoplay', '');
    video.setAttribute('muted', '');
    video.setAttribute('controls', '');
    video.style.background = '#000';
    video.style.display = 'block';
    video.style.outline = 'none';
    video.style.objectFit = 'contain';
    // Only show pause/play, hide seek/volume/fullscreen via CSS (already injected)
    // Clean up previous hls.js instance if any
    if (hlsPreviewInstance) {
      hlsPreviewInstance.destroy();
      hlsPreviewInstance = null;
    }
    // If same URL as last, just reload
    if (lastPreviewUrl === m3u8Url) {
      video.load();
    }
    lastPreviewUrl = m3u8Url;
    // HLS support check
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = m3u8Url;
      video.play().catch(()=>{});
    } else {
      // Dynamically load hls.js if not present
      function startHls() {
        hlsPreviewInstance = new window.Hls();
        hlsPreviewInstance.loadSource(m3u8Url);
        hlsPreviewInstance.attachMedia(video);
        hlsPreviewInstance.on(window.Hls.Events.ERROR, function (event, data) {
          video.poster = '';
          video.controls = false;
          video.style.background = '#000';
          video.src = '';
          preview.innerHTML = '<div style="color:#fff;padding:10px;">Failed to load stream preview.</div>';
        });
        video.play().catch(()=>{});
      }
      if (window.Hls) {
        startHls();
      } else {
        // Load hls.js from CDN
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.7/dist/hls.min.js';
        script.onload = startHls;
        script.onerror = function() {
          preview.innerHTML = '<div style="color:#fff;padding:10px;">Failed to load hls.js for preview.</div>';
        };
        document.head.appendChild(script);
      }
    }
    preview.appendChild(video);
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