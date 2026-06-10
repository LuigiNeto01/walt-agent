# walt-agent Instructions

## Project Rules

- Keep the backend API inside `backend/`.
- Keep the React frontend inside `frontend/`.
- Update `README.md`, `backend/README.md`, and this `AGENTS.md` whenever setup, commands, endpoints, Docker, or architecture change.
- Use Docker Compose for the local full stack: React frontend, FastAPI API, and PostgreSQL.
- Production deploys also use `docker-compose.prod.yml`; in production the API runs on host networking so Wake-on-LAN can leave through the server LAN.
- Persist chat conversations in PostgreSQL; do not rely only on OpenAI-hosted state.
- Keep API routes versioned under `/api/v1`.
- In Docker, keep frontend API calls relative through `/api/v1`; Nginx proxies `/api` to the FastAPI container.
- Conversation deletion is supported by `DELETE /api/v1/chat/conversations/{conversation_id}` and should remove related messages through ORM cascade.
- New chat titles are generated locally from the first user message by keeping the most relevant words short enough for the sidebar.
- Sidebar conversation items should stay compact, show the summarized title prominently, and keep destructive actions visually secondary until hover/focus.
- Wake-on-LAN lives in `POST /api/v1/tools/wake-pc` and can be used from chat through OpenAI function calling. Keep MAC/broadcast config in `.env`, never hardcode it.
- In multi-homed servers, Wake-on-LAN may optionally use `WAKE_SOURCE_IP` as a best-effort source-interface hint, but Docker bridge deploys must fall back gracefully if that IP is not present inside the container.
- Default chat persona is configured by `AGENT_SYSTEM_PROMPT`: the agent is Walt, responsible for managing Luigi's PC and tasks, with a friendly and helpful tone.
- Chat uses the OpenAI Responses API with native function calling. Walt decides autonomously when to use each tool. Do not add regex-based command detection in `chat_service.py`; all PC actions go through the 5 tools defined in `openai_chat_service.py`.
- Multi-step chat tasks should be handled by the Responses API loop: Walt plans internally, calls tools repeatedly, observes results, verifies completion, and only returns a final answer after the requested steps are complete or a real blocker is reached.
- The frontend uses `POST /api/v1/chat/stream` to show operational progress while Walt works. Show status, tool calls, and summarized tool results, but do not expose literal hidden chain-of-thought.
- SSH user is `walt` (technical local account), not `luigi`. Luigi's files are always at `C:\Users\luigi`; never use `%USERPROFILE%`, `~`, or `$HOME` in SSH commands for Luigi files.
- Always use forward slashes in Python script paths passed over SSH to avoid backslash escape corruption, for example `C:/Users/luigi/script.py`.
- To launch GUI scripts (pyautogui, tkinter, etc.) in Luigi's desktop session, use `run_python_script` with `background=true`. This triggers `_launch_in_desktop_session()` in `openai_chat_service.py`, which uploads `walt_launcher.py` to the PC and runs it as SYSTEM via Task Scheduler. The launcher uses `WTSQueryUserToken` and `CreateProcessAsUserW` to inject the process into the Console session. This requires Luigi to be logged in.
- `SSH_COMMAND_TIMEOUT` should be 120s in production to avoid nginx 504 on long-running SSH operations.
- `WAKE_VERIFY_SSH_TIMEOUT` and `WAKE_VERIFY_SSH_INTERVAL` control how long `wake_pc` waits for SSH to become reachable after sending Wake-on-LAN. Keep frontend Nginx proxy read/send timeouts high enough for wake-and-run chat flows.
- `deploy.py` must not hardcode API keys or passwords. It reads production settings from `backend/.env` and deployment credentials from `DEPLOY_*` environment variables or an interactive password prompt.
- `deploy.py` must not erase existing remote secrets or write blank typed settings into the remote `backend/.env`; preserve remote values when local ones are empty, otherwise omit empty typed fields so FastAPI/Pydantic can keep defaults.
- For Tailscale deploys, install/authenticate Tailscale on the server first, then run `deploy.py` with `DEPLOY_HOST` set to the server's Tailscale IPv4 address. If the deploy machine is not in the tailnet, keep `DEPLOY_HOST` as the LAN IP and set `DEPLOY_PUBLIC_HOSTS` to the Tailscale IPv4 address so production CORS includes it.

## Current Stack

- Backend: FastAPI
- Frontend: React + Vite
- Database: PostgreSQL in Docker Compose
- ORM: SQLAlchemy
- OpenAI integration: Responses API through the official Python SDK

## Useful Commands

```powershell
copy backend\.env.example backend\.env
docker compose up --build
```

Docs: `http://127.0.0.1:8000/docs`
Frontend: `http://127.0.0.1:5173`

Frontend dev:

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

Tests:

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest
```
