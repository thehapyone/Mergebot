# Mergebot Quickstart – Self-Hosted with GitHub App

Follow these steps to run Mergebot **ondemand** against your repositories using your own GitHub App.

---

## 1. Create a GitHub App

1. Go to **Settings → Developer settings → GitHub Apps → New GitHub App**.  
2. Fill in:
   * **App name**: e.g. `Mergebot Self-Hosted`
   * **Webhook URL**: `http://YOUR-HOST/webhook` (not used in ondemand but required)  
   * **Callback URL**: leave blank or placeholder (`https://example.com/unused`)
3. Permissions (Repository level)
   * Contents: **Read & write**
   * Pull requests: **Read & write**
   * Issues: **Read & write**
   * Checks: **Read & write** (optional)
4. Save, then **Generate a private key** → download `private-key.pem`.
5. Install the App on the repository/org you want Mergebot to manage.
   * Note the **App ID** (Settings page).
   * *Installation ID is optional* – Mergebot will auto-discover it.

---

## 2. Prepare environment variables

```bash
export GITHUB_APP_ID=123456               # your App ID
export GITHUB_APP_PRIVATE_KEY="$(cat private-key.pem)"
# Optional – only if auto-discovery fails
# export GITHUB_APP_INSTALLATION_ID=987654
```

You may instead set these keys in `mergebot/config.yaml` or `.mergebot.yml`:

```yaml
repository:
  type: github
  github:
    app_id: 123456
    private_key: |
      -----BEGIN RSA PRIVATE KEY-----
      YOUR-PEM-CONTENT-HERE
      -----END RSA PRIVATE KEY-----
    # installation_id: 987654   # optional
```

---

## 3. Run Mergebot ondemand

```bash
mergebot ondemand --project=owner/repo
```

Mergebot will:

1. Generate a JWT and exchange it for an installation access token.
2. Analyse open pull requests.
3. Comment / approve according to your `.mergebot.yml`.

---

## Troubleshooting

| Symptom | Resolution |
|---------|------------|
| `GitHub App credentials missing…` | Ensure `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` are set or in config. |
| `Could not determine installation_id` | Pass `GITHUB_APP_INSTALLATION_ID` env var (see **Installations** page URL). |
| 401/403 errors | Check that the App is installed on the target repo and has correct permissions. |
| Private key path error | Provide full path or inline PEM via env. |

---

You are now ready to automate PR reviews with your self-hosted Mergebot!
