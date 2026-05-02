# Go-live checklist (safe rollout)

Date: 2026-05-01

## Goal

Enable live publishing safely with explicit approval flow:
Draft -> approve -> publish.

## 1) Secrets and access

- Keep secrets only in local .env, never in repository or chat.
- Start from .env.example and fill only the channels you plan to enable first.
- Minimum required for drafting:
  - NVIDIA_API_KEY
- X remains manual in current setup:
  - X_API_KEY
  - X_API_SECRET
  - X_ACCESS_TOKEN
  - X_ACCESS_TOKEN_SECRET
- Required for LinkedIn publish:
  - LINKEDIN_ACCESS_TOKEN
  - LINKEDIN_AUTHOR_URN
- Instagram remains manual in current setup:
  - IG_ACCESS_TOKEN
  - IG_USER_ID
  - IG_IMAGE_HOST_ALLOWLIST
- Required for Bluesky publish:
  - BLUESKY_IDENTIFIER
  - BLUESKY_APP_PASSWORD
  - BLUESKY_SERVICE_URL (default https://bsky.social)
  - BLUESKY_SESSION_FILE (default ~/.nemo-bot/bluesky-session.json)

## 2) Safe defaults before live

- Keep DRY_RUN=true during setup and testing.
- Keep ALLOW_SCHEDULED_AUTOPUBLISH=false.
- Keep scheduled jobs in queue mode unless there is a separate go-live decision.

## 3) Validate with dry-run first

Run these with DRY_RUN=true:

- nemo-bot generate --topic "Kalma test" --details "Atmosphere post test" --platforms x
- nemo-bot review queue --topic "Kalma test" --details "Atmosphere post test" --platforms x
- nemo-bot review list --status pending --limit 10
- nemo-bot review show DRAFT_ID
- nemo-bot review approve DRAFT_ID
- nemo-bot review publish DRAFT_ID

Expected result in dry-run: publish command completes without live network post ID.

## 4) Approval policy

- Always require explicit user approval before publish.
- Reject or reopen drafts that need edits.
- Do not bypass review commands.

Approved workflow commands:

- nemo-bot review queue ...
- nemo-bot review show DRAFT_ID
- nemo-bot review edit DRAFT_ID --text "..."
- nemo-bot review approve DRAFT_ID
- nemo-bot review publish DRAFT_ID

## 5) Live enablement (one platform at a time)

- Enable only one channel first (recommended: Bluesky).
- Set DRY_RUN=false only when first live test is ready.
- Publish one approved draft.
- Verify platform result ID and account-side visibility.
- If good, continue to next channel.

## 6) Safety rules in effect

- Repost and quote-post markers are blocked by hard fail in pre-publish safety checks.
- Bluesky publishes through the same draft -> approve -> publish gate as other API channels.
- Reply and like actions stay manual and capped by plan defaults.

## 7) Rollback plan

If anything looks wrong:

- Immediately set DRY_RUN=true.
- Stop scheduled publishing by keeping ALLOW_SCHEDULED_AUTOPUBLISH=false.
- Revoke affected platform token.
- Rotate token and re-test in dry-run before next live attempt.

## 8) Recommended first live test

- Channel: Bluesky only
- Content: one short atmosphere post
- Process: queue -> show -> approve -> publish
- Follow-up: confirm post appears on account and log the publish ID
