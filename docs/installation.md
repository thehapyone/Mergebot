# Installation

How to install and set up Mergebot.

## Requirements

- Python 3.12+ (if running from source)
- Docker (containerized usage)
- GitHub or GitLab account and project access


## Install via Docker

```bash
docker pull thehapyone/mergebot:latest
```

## Clone from Source

```bash
git clone https://github.com/thehapyone/Mergebot.git
cd Mergebot

poetry install

## Run the app
mergebot ondemand  --project=path_to_your_github_or_gitlab_project
```

---

> **Note:** Mergebot fully supports both GitHub and GitLab projects.
>
> For quick setup, see [Quickstart](quickstart.md).

---

## GitHub App Setup (Recommended for Service User Mode)

To run Mergebot as a true service user (not on behalf of a personal account), use a GitHub App:

1. **Create a GitHub App**
   - Go to your organization or user settings → Developer settings → GitHub Apps → New GitHub App.
   - **Callback URL vs Webhook URL**  
     *They are different fields:*  
     • **Callback URL** is only used when your App requests *user*-authorization (OAuth). Mergebot does **not** use that flow, so you may leave it blank or set a placeholder such as `https://example.com/unused-callback`.  
     • **Webhook URL** must point to your Mergebot endpoint, e.g. `https://your-mergebot.example.com/webhook`.
   - Set a name, homepage, and the webhook URL as above.
   - **Permissions:**
     - Contents: Read & write
     - Pull requests: Read & write
     - Issues: Read & write
     - Checks: Read & write (optional, for CI status)
     - Metadata: Read-only (always granted)
   - **Webhooks:** Subscribe to `pull_request`, `issue_comment`, and any others Mergebot should react to.
   - Save and generate a private key (PEM file).

2. **Install the App**
   - Install the App on the target repository or organization.

3. **Configure Mergebot**
   - In your config, supply:
     ```yaml
     repository:
       type: "github"
       github:
         base_branch: "main"
         app_id: <your-app-id>
         installation_id: <your-installation-id>  # optional; auto-discovered if omitted
         private_key: <private key>  # or set GITHUB_APP_PRIVATE_KEY env
     ```
   - You can also set these as environment variables: `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`.

4. **Migration Notes**
   - If you previously used a personal access token (`GITHUB_TOKEN`), you may keep it for backward compatibility, but it is **deprecated**.
   - Mergebot will use the App credentials if both are present.
   - The App acts on its own behalf, not as a user, and all actions are attributed to the App.

5. **Security**
   - Never share your App’s private key.


For more details, see [Onboarding](usage/onboarding.md) and [Configuration Schema](configuration/config_schema.md).
