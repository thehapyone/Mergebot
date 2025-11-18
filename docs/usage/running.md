# Ways to Run Mergebot

Mergebot enables code review automation for your GitHub or GitLab projects.
This page helps **users** quickly integrate Mergebot—the default: _no local install required_.

---

## The Normal Way: Use Mergebot as a Service or in CI

For **most users**, the recommended path is to integrate Mergebot with your existing repository, via CI/CD or the (coming soon) cloud offering.

### 1. Use in GitHub Actions or GitLab CI

- **GitHub Actions:**
  Add or copy a workflow using the Docker image. See [GitHub Actions Guide](../operations/github_actions.md)

- **GitLab CI:**
  Add a job to your `.gitlab-ci.yml` referencing the Docker image. See [GitLab CI Guide](../operations/gitlab_ci.md)

_All examples use the official Docker image: `thehapyone/mergebot:latest`_

---

### 2. (Coming soon) Cloud-Hosted Mode

Activate Mergebot via a web UI, no infrastructure required.
Stay tuned for release updates!

---

## Minimal Local “Installation” for Advanced Usage

> ⚠️ This is for advanced users/contributors or for manual/standalone use.
> **Most users do NOT need to install Mergebot locally!**

- **Docker (recommended for all platforms):**
    ```bash
    docker pull thehapyone/mergebot:latest
    ```
- **From source (for contributions or debugging only):**
    ```bash
    git clone https://github.com/thehapyone/Mergebot.git
    cd Mergebot
    poetry install
    ```

---

## Other Ways to Run

- **Direct CLI invocation:**
  Useful for scripting, advanced workflows, or debugging.
  See [CLI Reference](cli_reference.md) for full details.

### Multi-Project Operation

- Define repositories under `repository.projects` (see [Configuration Schema](../configuration/config_schema.md#multi-project-configuration-optional)). Each entry specifies the repository `path`, an optional `webhook.secret`, and any overrides.
- The webhook server automatically dispatches events based on the repository identifier in the payload and enforces per-project secrets.
- Ondemand mode fans out across the same project list; use `--max-concurrency` to control how many repositories are processed simultaneously.
- Each ondemand sweep logs the number of projects discovered and the effective concurrency cap, and offloads `.mergebot.yml` loading to a background thread to keep the async runners responsive.
- CLI flags no longer require `--project`; configuration is the single source of truth.

## Project Session Lock

To prevent duplicate analysis/comments across multiple Mergebot instances for the same repository, Mergebot uses a project-level session lock:

- Scope: one active session per project at a time (applies to both ondemand and webhook-triggered runs).
- Storage: persisted in the Dashboard issue under the “Active Session” section (between MERGEBOT_SESSION_LOCK markers).
- Default TTL: 10 minutes. While a run is active, a heartbeat extends the lock so it won’t expire mid-run.
- Crash safety: if a runner crashes, the lock expires after TTL and future runs proceed.
- Identity: Mergebot uses hostname-pid-uuid.

Behavior:
- If another instance holds the lock, new runs will skip with a log message like “session lock is held by another instance”.
- The Dashboard layout always shows a single “Active Session” header; the lock JSON is rendered underneath.

---

## Local Webhook Testing (Ngrok or similar tunnels)

Need to exercise webhook mode from a laptop or CI sandbox? Use a tunnelling service (e.g., [Ngrok](https://ngrok.com), Cloudflare Tunnels, GitHub Codespaces forwarding) to expose your local FastAPI server to GitHub or GitLab:

1. Start the webhook server locally:
   ```bash
   poetry run mergebot webhook --port 8000 --max-concurrency 1
   ```
2. Run a tunnel pointing to the same port:
   ```bash
   ngrok http http://localhost:8000
   ```
   Copy the generated `https://<random>.ngrok.app/webhook` URL.
3. Configure the GitHub/GitLab webhook with that public URL and reuse the same secret defined in your Mergebot config (or project-level override).
4. Trigger events (e.g., open an MR/PR or post `/mergebot review`). Ngrok will forward them to your local Mergebot instance so you can iterate rapidly.

**Security tips:**
- Keep the tunnel temporary and rotate the webhook secret after public demos.
- Use Ngrok’s IP allow-listing or basic auth when possible.
- Stop the tunnel when you finish testing so external services can’t reach a stale localhost instance.

---

## Next Steps

1. **Set up your credentials/bot:**
   See [Onboarding Guide](onboarding.md)
2. **See or copy a real workflow (GitHub/GitLab):**
   - [GitHub Actions Example](../operations/github_actions.md)
   - [GitLab CI Example](../operations/gitlab_ci.md)
3. **Want just the quickest guide?**
   Try [Quickstart](../quickstart.md)

---

_If you want to contribute to Mergebot itself, see the [Contributing Guide](../contributing.md)._
