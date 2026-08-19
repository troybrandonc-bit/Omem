# Provider verification checklist

Everything below is REAL CODE wired end-to-end but NOT provider-verified in the
build environment (no egress/credentials). Each section lists the exact env vars
and the verification steps.

## Gmail (Google OAuth)
Env: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
1. Create OAuth credentials at console.cloud.google.com (Gmail API enabled,
   scope `gmail.readonly`, redirect = your `/oauth/gmail/callback`).
2. Start the server with the env set; `POST /v1/oauth/gmail/begin` now returns a
   real Google consent URL (signed state included).
3. Complete consent; the callback exchanges the code at oauth2.googleapis.com
   (`real_exchange: true` in the response), stores tokens AES-GCM-encrypted.
4. `POST /v1/connectors/{id}/poll` pulls real messages via gmail.googleapis.com
   (pagination + 429 backoff built in). Verify: recall the produced memory and
   open `/why` back to the message id.

## LLM extraction
Env: `OMEM_LLM_API_KEY`, `OMEM_LLM_BASE_URL` (default OpenAI), `OMEM_LLM_MODEL`
1. Set the env (any OpenAI-compatible endpoint: OpenAI, Together, Groq, vLLM).
2. Per project: `POST /v1/settings {"llm_enabled":"1","llm_model":"..."}`.
3. Ingest any source; check `/v1/extraction-logs` for the extractor+model and
   `/v1/usage` for `llm_tokens`. Evidence validation drops hallucinated facts.

## Stripe
Env: `STRIPE_SECRET_KEY` (test mode), `STRIPE_WEBHOOK_SECRET`
1. `POST /v1/billing/checkout` creates a real test-mode customer.
2. Point a Stripe webhook at `/v1/billing/webhook`; signature verification and
   the subscription lifecycle (active/cancelled/past_due) are already verified
   locally against Stripe's documented HMAC scheme.

## Slack
Env: none server-wide; per-connector bot token stored via OAuth store.
1. Create a Slack app with `channels:history`; install to workspace.
2. Save the bot token for the connector, set `config.channel`; poll pulls real
   conversations.history (transport already speaks the real wire shape).

## Salesforce
Env: `SFDC_INSTANCE_URL`
1. Connected App with API scope; store the access token for the connector.
2. Poll queries Note records via SOQL through /services/data.
