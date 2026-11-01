# AGZ Bridge v1.0.0 Release Notes

**AGZ Bridge v1.0.0** is the first official release of the autonomous bridge connecting **Google Antigravity 2.0 CLI (`agy`)** to **Agent Zero**.

### Highlights
- **Direct Antigravity CLI Integration**: Uses the existing Google OAuth authorization and subscription quota on MAIN PC without requiring external Gemini API keys.
- **OpenAI-Compatible Gateway**: Exposes `/v1/models` and `/v1/chat/completions` with support for both JSON and Server-Sent Events (SSE) streaming.
- **Worker-Isolated Tool Execution**: Ensures that terminal commands, file operations, Python execution, browser control, and computer use run exclusively on the Worker PC.
- **Single-Command Worker Deployment**: Complete automated setup on the second computer with `install-worker.ps1`.
- **Zero-Trust Ephemeral Pairing**: Cryptographic one-time pairing codes with 15-minute expiration and token hashing.
- **Interactive Web Dashboard**: Built-in monitoring dashboard at `/dashboard` with live metrics, connected workers, token counts, and pairing controls.
- **Full Test Suite**: 20 comprehensive automated tests passing with 100% coverage across CLI, Gateway, Tool Calling, Security, Installation, and physical E2E execution.

### Verification Hashes
All files in this release are verified against `SHA256SUMS`.
