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
