# Ollama and AI Setup

This doc covers fixing the “same output every time” issue, using API keys, per-device Ollama, and making the AI useful for blocks, timers, and web search.

---

## Fix: “Same output every time”

**Cause:** The desktop was calling Ollama’s `/api/generate` with only the user message. Some models behave poorly without a system prompt and proper chat format.

**Fix:** The desktop now uses Ollama’s **`/api/chat`** with:

- A **system** message (you are Aion, answer the user, never repeat the same reply).
- The **user** message (what the user actually typed).

So each request is clearly tied to the current input and the model can respond correctly.

**Backend:** The backend has always used `/api/chat` with system + RAG + user message; no change needed there.

---

## Where the AI runs

- **Desktop (this PC):**
  - **Local Ollama:** Uses `ollama_generate` (Tauri) → `http://127.0.0.1:11434/api/chat` by default.
  - **Backend AI:** If “Use backend for AI” is on in Settings, the desktop calls the backend `/api/v1/ai/chat` (RAG + optional web search + API keys).
- **Backend (this PC):**
  - Uses **Ollama** at `OLLAMA_HOST:OLLAMA_PORT` (default localhost:11434), or
  - **OpenAI** / **Anthropic** if the corresponding API key and `AI_PROVIDER` are set.

So “Ollama mainly comes from this Windows computer” = run Ollama and the backend on the Windows PC; other devices can use the same backend (and thus the same Ollama or cloud AI).

---

## Other devices with their own Ollama

- **Tablet/phone using Windows backend:**  
  Point the app at the Windows backend URL. AI runs on the backend (Windows Ollama or cloud). No local Ollama on the device.

- **Device with Ollama installed:**  
  On that device you can run `ollama serve` and then:
  - **Backend on that device:** Set `OLLAMA_HOST=localhost` (or that device’s IP) and `OLLAMA_PORT=11434` in the backend `.env`.
  - **Desktop on that device:** In Aion Settings → AI → “Ollama URL”, set e.g. `http://127.0.0.1:11434` (or the device’s LAN IP) so the desktop uses that device’s Ollama instead of the Windows PC.

---

## API keys (optional)

To use OpenAI or Anthropic instead of (or as well as) Ollama:

1. **Backend** (`.env`):
   - `OPENAI_API_KEY=sk-...` and/or `ANTHROPIC_API_KEY=sk-ant-...`
   - `AI_PROVIDER=openai` or `AI_PROVIDER=anthropic` (default is `ollama`).

2. **Desktop:**  
   Turn on **“Use backend for AI”** in Settings so chat goes to the backend; the backend will use the configured provider and keys.

3. **Models:**  
   With API keys, the backend’s model list and chat use the corresponding provider (e.g. `gpt-4o-mini`, `claude-3-5-sonnet`). The desktop model dropdown is filled from the backend when you use backend AI.

---

## What the AI can do

- **Create blocks, tasks, timetables, start timers:**  
  The desktop already handles phrases like “create block”, “add task”, “start 25 minute timer”, “create a timetable”, “I need to study for …”. Those are handled locally and don’t depend on Ollama. The AI (Ollama or backend) is used for everything else (answers, suggestions, follow-up).

- **Web / Google-style answers:**  
  When the desktop uses **backend AI** and you enable **web search** (it’s on by default for the backend chat call), the backend runs a web search and injects the results into the AI context so it can use up-to-date information.

- **Database / “manage everything”:**  
  The backend chat uses RAG over your blocks (and optional web search). It can’t directly edit the DB; it can suggest actions and you (or future tool-calling) can apply them. Direct DB changes are not exposed to the model for safety.

---

## Optimization

- **Desktop Ollama call:**  
  Uses `temperature: 0.7` and `num_predict: 2048`, and a 120s timeout.

- **Backend:**  
  Same idea: temperature and length are set in the chat call. For heavy load, run Ollama with enough RAM and prefer a smaller/faster model (e.g. `llama3.2` or `phi`).

- **API keys:**  
  For speed/cost you can use a smaller cloud model (e.g. `gpt-4o-mini`) and keep Ollama for local or fallback.

---

## Double-check list

- [ ] Desktop: Typing different messages in the AI bar gives **different** replies (fix for “same output”).
- [ ] Desktop: Settings → AI → “Use backend for AI” and “Ollama URL” are set as you want (backend vs local/device Ollama).
- [ ] Backend: `.env` has `OLLAMA_HOST` / `OLLAMA_PORT` (and optional `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` + `AI_PROVIDER`).
- [ ] Other devices: Either use the Windows backend URL only, or run backend + Ollama on the device and set `OLLAMA_HOST` / desktop “Ollama URL” accordingly.
