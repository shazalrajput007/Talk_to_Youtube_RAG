const API = {
  process: "/api/videos",
  chat: "/api/chat",
  clear: "/api/chat/clear",
};

// ---- DOM elements ----
const urlForm = document.getElementById("url-form");
const urlInput = document.getElementById("url-input");
const processBtn = document.getElementById("process-btn");
const statusEl = document.getElementById("status");
const videoInfo = document.getElementById("video-info");
const videoTitle = document.getElementById("video-title");
const videoStatus = document.getElementById("video-status");
const chatBox = document.getElementById("chat-box");
const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");

// ---- State ----
function getSessionId() {
  let id = sessionStorage.getItem("ytrag_session_id");
  if (!id) {
    id = crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem("ytrag_session_id", id);
  }
  return id;
}

const state = {
  videoId: null,
  sessionId: getSessionId(),
  busy: false,
};

// ---- Helpers ----
async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    /* non-JSON response */
  }

  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
  }
  return data;
}

function setStatus(message, type = "info") {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}

function setBusy(isBusy) {
  state.busy = isBusy;
  const ready = Boolean(state.videoId);
  processBtn.disabled = isBusy;
  sendBtn.disabled = isBusy || !ready;
  questionInput.disabled = isBusy || !ready;
  clearBtn.disabled = isBusy || !ready;
}

function removeEmptyState() {
  const empty = chatBox.querySelector(".empty");
  if (empty) empty.remove();
}

function scrollToBottom() {
  chatBox.scrollTop = chatBox.scrollHeight;
}

function resetChat() {
  chatBox.innerHTML = "";
}

function addMessage(role, text, sources = []) {
  removeEmptyState();

  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text; // textContent prevents XSS
  wrapper.appendChild(bubble);

  if (sources && sources.length) {
    const list = document.createElement("div");
    list.className = "sources";

    const label = document.createElement("span");
    label.className = "sources-label";
    label.textContent = "Sources:";
    list.appendChild(label);

    sources.forEach((src) => {
      const link = document.createElement("a");
      link.href = src.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "source-chip";
      link.textContent = `▶ ${src.timestamp}`;
      link.title = src.text;
      list.appendChild(link);
    });

    wrapper.appendChild(list);
  }

  chatBox.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function showTyping() {
  removeEmptyState();
  const wrapper = document.createElement("div");
  wrapper.className = "message assistant";
  wrapper.innerHTML = `
    <div class="bubble typing"><span></span><span></span><span></span></div>`;
  chatBox.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

// ---- Event: process a video ----
urlForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  setBusy(true);
  setStatus("Fetching transcript and building the index… this may take a moment.", "info");

  try {
    const data = await postJSON(API.process, { url });

    // Reset server-side memory for this video so the new session starts fresh.
    if (state.videoId) {
      postJSON(API.clear, { video_id: state.videoId, session_id: state.sessionId }).catch(() => {});
    }

    state.videoId = data.video_id;
    videoTitle.textContent = data.title || `Video ${data.video_id}`;
    videoStatus.textContent = data.cached ? "Already indexed" : "Ready";
    videoInfo.classList.remove("hidden");
    setStatus(data.message, "success");

    resetChat();
    addMessage("assistant", "The video is ready. Ask me anything about it!");
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    setBusy(false);
  }
});

// ---- Event: send a question ----
chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !state.videoId || state.busy) return;

  questionInput.value = "";
  addMessage("user", question);

  const typing = showTyping();
  setBusy(true);

  try {
    const data = await postJSON(API.chat, {
      video_id: state.videoId,
      session_id: state.sessionId,
      question,
    });
    typing.remove();
    addMessage("assistant", data.answer, data.sources);
  } catch (err) {
    typing.remove();
    addMessage("assistant", `⚠️ ${err.message}`);
  } finally {
    setBusy(false);
    questionInput.focus();
  }
});

// ---- Event: clear chat ----
clearBtn.addEventListener("click", async () => {
  if (!state.videoId) return;
  setBusy(true);
  try {
    await postJSON(API.clear, { video_id: state.videoId, session_id: state.sessionId });
    resetChat();
    addMessage("assistant", "Chat cleared. Ask a new question!");
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    setBusy(false);
  }
});

// ---- Init ----
setBusy(false);