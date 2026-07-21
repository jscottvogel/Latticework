# Deployment Notes — Buffett Screener

This document details how to configure and deploy the Buffett Screener backend and frontend.

## Secrets Manager Configuration

For security, the orchestrator Function URL requires a shared secret. You must create the following secret in AWS Secrets Manager:

### 1. Trigger Secret (`/buffett-screener/trigger-secret`)
Create this secret using the AWS CLI or the AWS Secrets Manager console:

```bash
aws secretsmanager create-secret \
  --name /buffett-screener/trigger-secret \
  --secret-string '{"key": "YOUR_GENERATED_SECURE_TRIGGER_SECRET"}'
```

*Replace `YOUR_GENERATED_SECURE_TRIGGER_SECRET` with a secure random string of your choice.*

## Frontend Environment Configuration

The React frontend requires this secret to authenticate requests when triggering a run manually.

During the Vite build process, set the `VITE_TRIGGER_SECRET` environment variable to the same value as the secret created above:

```bash
# Example for local development / manual build
$env:VITE_TRIGGER_SECRET="YOUR_GENERATED_SECURE_TRIGGER_SECRET"
npm run build
```

If deploying via Amplify Console, add `VITE_TRIGGER_SECRET` as an environment variable in **App settings > Environment variables** in the AWS Amplify Console.
