# Using Mergebot in GitLab CI

Mergebot is designed to be run as part of your GitLab CI/CD pipelines, either:
- As a job in merge request pipelines (recommended for per-MR analysis)
- As a scheduled pipeline in a dedicated project (for batch or multi-project analysis)

## 1. Merge Request Pipeline Example

Add the following to your `.gitlab-ci.yml` in your project:

```yaml
stages:
  - mergebot

mergebot:
  stage: mergebot
  image: thehapyone/mergebot:latest
  script:
    - mergebot ondemand --project $CI_PROJECT_PATH --workers 4
  only:
    - merge_requests
  variables:
    GITLAB_PERSONAL_ACCESS_TOKEN: $GITLAB_PERSONAL_ACCESS_TOKEN
```

- This job runs Mergebot for the current project on every merge request pipeline.
- Make sure to set the `GITLAB_PERSONAL_ACCESS_TOKEN` as a CI/CD variable in your project settings.

## 2. Scheduled Pipeline for Multiple Projects

You can also set up a dedicated GitLab project to run Mergebot on a schedule for multiple repositories:

```yaml
stages:
  - mergebot

mergebot:
  stage: mergebot
  image: thehapyone/mergebot:latest
  script:
    - mergebot ondemand --project group1/project1 --workers 4
    - mergebot ondemand --project group2/project2 --workers 4
  only:
    - schedules
  variables:
    GITLAB_PERSONAL_ACCESS_TOKEN: $GITLAB_PERSONAL_ACCESS_TOKEN
```

- Schedule this pipeline in the CI/CD > Schedules section.
- Add as many `mergebot ondemand --project ...` lines as needed for your projects.

## 3. Best Practices

- Always use environment variables for sensitive tokens.
- Use the official Docker image for reproducibility.
- For large organizations, consider a dedicated Mergebot runner project.

## 4. Example .gitlab-ci.yml Template

```yaml
stages:
  - mergebot

mergebot:
  stage: mergebot
  image: thehapyone/mergebot:latest
  script:
    - mergebot ondemand --project $CI_PROJECT_PATH --workers 4
  only:
    - merge_requests
  variables:
    GITLAB_PERSONAL_ACCESS_TOKEN: $GITLAB_PERSONAL_ACCESS_TOKEN
```

> For more advanced usage, see the [Quickstart](../quickstart.md) and [Onboarding](../usage/onboarding.md) guides.
