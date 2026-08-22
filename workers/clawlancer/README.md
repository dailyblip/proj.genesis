# Ultra Genesis — Clawlancer Worker

A safe-by-default scheduled worker for Clawlancer.

## What it does

- scans live Clawlancer bounties every 15 minutes via GitHub Actions
- recognizes only a small whitelist of deterministic tasks it can fulfill reliably
- dry-runs by default
- when explicitly enabled, claims at most one whitelisted bounty per run and submits the generated deliverable
- never buys services, funds wallets, withdraws funds, posts listings, or sends unsolicited messages

## Required secret

Repository **Settings → Secrets and variables → Actions → Secrets → New repository secret**

- `CLAWLANCER_API_KEY` = your Clawlancer agent API key

Do not put the key in source code, issues, logs, or chat.

## Live-mode variable

Repository **Settings → Secrets and variables → Actions → Variables → New repository variable**

- `CLAWLANCER_LIVE` = `true`

Optional variables:

- `CLAWLANCER_MAX_CLAIMS` = `1` (default)
- `CLAWLANCER_MIN_REWARD_USDC` = `0.01` (default)

Without `CLAWLANCER_LIVE=true`, the worker only scans and logs candidates.

## Safety model

Clawlancer is a beta service using real USDC. This worker deliberately does not expose withdrawal, purchase, funding, listing-creation, messaging, dispute, refund, or wallet-management actions. Live mode is restricted to pre-funded bounty claim + delivery for known bounded task types.
