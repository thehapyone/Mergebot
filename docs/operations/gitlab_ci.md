# Using Mergebot in GitLab CI

Mergebot is designed to be run as part of your GitLab CI/CD pipelines, either:

- As a job in merge request pipelines
- As a scheduled pipeline in a dedicated project (for batch or multi-project analysis) (recommended)

## 1. Merge Request Pipeline Example

Add the following to your `.gitlab-ci.yml` in your project:

```yaml
stages:
  - deploy

mergebot:
  stage: deploy
  image: thehapyone/mergebot:latest
  script:
    - mergebot ondemand --project $GITLAB_PROJECT_PATH --workers 10
  variables:
    GITLAB_PROJECT_PATH: $CI_PROJECT_PATH
    REQUESTS_CA_BUNDLE: $CA_BUNDLE
    GITLAB_PERSONAL_ACCESS_TOKEN: $MERGEBOT_TOKEN
    CONFIG_PATH: "$CI_PROJECT_DIR/mergebot-config.yml"
    # Azure API Configuration
    AZURE_API_KEY: my_api_key
    AZURE_API_BASE: "https://myinstance.openai.azure.com"
    AZURE_API_VERSION: "2025-04-01-preview"
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

- This job runs Mergebot for the current project on every merge request pipeline.
- Make sure to set the `GITLAB_PERSONAL_ACCESS_TOKEN` as a CI/CD variable in your project settings.

## 2. Scheduled Pipeline for Multiple Projects

You can also set up a dedicated GitLab project to run Mergebot on a schedule for multiple repositories:

```yaml
stages:
  - deploy

mergebot:
  stage: deploy
  image: thehapyone/mergebot:latest
  script:
    - mergebot ondemand --project $GITLAB_PROJECT_PATH --workers 10
  parallel:
    matrix:
      # use mergebot for various projects
      - GITLAB_PROJECT_PATH:
          - group1/project1
          - group3/project3
          - group4/project
  variables:
    REQUESTS_CA_BUNDLE: $CA_BUNDLE
    GITLAB_PERSONAL_ACCESS_TOKEN: $MERGEBOT_TOKEN
    CONFIG_PATH: "$CI_PROJECT_DIR/mergebot-config.yml"
    # Azure API Configuration
    AZURE_API_KEY: my_api_key
    AZURE_API_BASE: "https://myinstance.openai.azure.com"
    AZURE_API_VERSION: "2025-04-01-preview"
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
```

- Schedule this pipeline in the CI/CD > Schedules section.
- Add as many `mergebot ondemand --project ...` lines as needed for your projects.

## 3. Best Practices

- **Always use environment variables for sensitive tokens.**
- **Create a dedicated GitLab service account for Mergebot:**
  - It is strongly recommended to create a dedicated GitLab user (e.g., `mergebot`) to act as a bot/service account.
  - Generate a personal access token for this service account and use it as the `GITLAB_PERSONAL_ACCESS_TOKEN` (e.g., store as the `MERGEBOT_TOKEN` CI/CD variable).
  - Add this service account as a member to the relevant project(s) or group(s) with the minimum required permissions.
  - _Do not use a personal user’s API token_, as this will make it appear that user is performing all Mergebot actions.
  - **Alternative:** You may use a [Project Bot](https://docs.gitlab.com/ee/user/project/bot_users.html), but note that project bots cannot be reused across multiple projects. For most organizations, a dedicated service account at the instance or group level is preferred.
- Use the official Docker image for reproducibility.
- For large organizations, consider a dedicated Mergebot runner project.

> For more advanced usage, see the [Quickstart](../quickstart.md) and [Onboarding](../usage/onboarding.md) guides.
