let eventSource = null;
let currentActor = null;   // Tracks active speaker
let isRightSide = false;   // Flips layout only when currentActor changes
let currentAudio = null;   // Keeps track of active background audio instance
let currentDubbedAudio = null; // Keeps track of the active dubbed/cloned-voice clip

let sharedDubbedAudio = new Audio();

// A single silent sample, used only to unlock sharedDubbedAudio for iOS
// Safari (see startStream below). Generated/verified locally as a minimal
// valid 1-sample WAV -- not a placeholder.
const SILENT_AUDIO_DATA_URL =
    "data:audio/wav;base64,UklGRiUAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQEAAACA";

function startStream(selectedLanguage) {
    document.getElementById('selection-modal').classList.add('hidden');
    document.getElementById('live-indicator').classList.remove('hidden');
    document.getElementById('live-indicator').classList.add('flex');

    // Unlock sharedDubbedAudio for iOS Safari. A mere .load() does NOT
    // satisfy iOS's autoplay policy -- it specifically requires an actual
    // .play() call to happen synchronously inside a real user gesture
    // (this click/tap). Later, playDubbedVoice() calls .play() from inside
    // an SSE event handler, which fires asynchronously and is NOT a user
    // gesture -- without this unlock, iOS silently blocks that .play()
    // (captions still render fine since those are just DOM updates, so the
    // failure is easy to miss: text works, audio silently doesn't).
    // Playing a real (silent) clip here, then immediately pausing, is the
    // standard unlock trick; swapping .src later for a real clip and
    // calling .play() again then succeeds, since it's the same element.
    sharedDubbedAudio.src = SILENT_AUDIO_DATA_URL;
    sharedDubbedAudio.play()
        .then(() => {
            sharedDubbedAudio.pause();
            sharedDubbedAudio.currentTime = 0;
        })
        .catch((error) => {
            console.warn("Audio unlock attempt failed (may still work on non-iOS browsers):", error);
        });

    const streamUrl = `/api/v1/stream?lang=${encodeURIComponent(selectedLanguage)}`;
    eventSource = new EventSource(streamUrl);

    eventSource.onmessage = function (event) {
        const payload = JSON.parse(event.data);
        renderChatBubble(payload);
    };

    eventSource.addEventListener('audio', function (event) {
        const payload = JSON.parse(event.data);
        if (payload.audio_url) {
            playDubbedVoice(payload.audio_url);
        }
    });

    eventSource.onerror = function (error) {
        console.error("SSE Stream disconnected or ended.", error);
        eventSource.close();
    };
}

function playDubbedVoice(audioUrl) {
    // Reuse the persistent audio element and update its source
    sharedDubbedAudio.pause();
    sharedDubbedAudio.currentTime = 0;
    sharedDubbedAudio.src = audioUrl;

    sharedDubbedAudio.play().catch((error) => {
        console.warn(`Dubbed audio playback skipped for ${audioUrl}:`, error);
    });
}

function playBackgroundVoice(actor, lineId) {
    // Stop previous line audio if it is still playing
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
    }

    // Construct filename: e.g. /static/voice/ALADDIN_1.mp3
    const voiceFileName = `${actor}_${lineId}.wav`;
    const audioUrl = `/static/voice/${encodeURIComponent(voiceFileName)}`;

    currentAudio = new Audio(audioUrl);

    // Play sound headlessly in the background
    currentAudio.play().catch((error) => {
        // Silently catch missing audio files or browser autoplay restrictions
        console.warn(`Audio playback skipped for ${voiceFileName}:`, error);
    });
}

function renderChatBubble(data) {
    const chatContainer = document.getElementById('chat-container');

    if (data.scene_id) {
        document.getElementById('scene-tag').innerText = data.scene_id;
    }

    const newActor = (data.actor || 'NATIVE').trim().toUpperCase();
    const imageFilename = newActor.toLowerCase() + '.png';
    const avatarUrl = `/static/images/actors/${imageFilename}`;

    // Flip alignment ONLY when a different actor takes a turn
    if (currentActor !== null && newActor !== currentActor) {
        isRightSide = !isRightSide;
    }

    // Lock in active actor
    currentActor = newActor;

    const messageNode = document.createElement('div');

    if (isRightSide) {
        // RIGHT SIDE
        messageNode.className = 'flex justify-end w-full animate-fade-in';
        messageNode.innerHTML = `
            <div class="flex items-start gap-3 max-w-[85%] sm:max-w-[75%] flex-row-reverse">
                <img src="${avatarUrl}"
                     onerror="this.onerror=null; this.src='/static/images/actors/default.png';"
                     alt="${newActor}"
                     class="w-10 h-10 rounded-full object-cover border border-amber-400/50 flex-shrink-0 bg-slate-800">
                <div class="bg-amber-950/30 border border-amber-800/50 p-3.5 rounded-2xl rounded-tr-none text-right">
                    <div class="mb-1">
                        <span class="text-xs font-bold font-mono tracking-wider text-amber-400">${newActor}</span>
                    </div>
                    <p class="text-sm sm:text-base text-slate-100 leading-relaxed">${data.text}</p>
                </div>
            </div>
        `;
    } else {
        // LEFT SIDE
        messageNode.className = 'flex justify-start w-full animate-fade-in';
        messageNode.innerHTML = `
            <div class="flex items-start gap-3 max-w-[85%] sm:max-w-[75%] flex-row">
                <img src="${avatarUrl}"
                     onerror="this.onerror=null; this.src='/static/images/actors/default.png';"
                     alt="${newActor}"
                     class="w-10 h-10 rounded-full object-cover border border-amber-400/50 flex-shrink-0 bg-slate-800">
                <div class="bg-slate-900 border border-slate-800 p-3.5 rounded-2xl rounded-tl-none text-left">
                    <div class="mb-1">
                        <span class="text-xs font-bold font-mono tracking-wider text-amber-400">${newActor}</span>
                    </div>
                    <p class="text-sm sm:text-base text-slate-100 leading-relaxed">${data.text}</p>
                </div>
            </div>
        `;
    }

    chatContainer.appendChild(messageNode);

    // Trigger headless audio playback in background
    if (data.actor && data.line_id) {
        playBackgroundVoice(data.actor.trim(), data.line_id);
    }

    // Auto-scroll to bottom
    setTimeout(() => {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }, 50);
}