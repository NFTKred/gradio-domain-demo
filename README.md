# Domains.Kred MCP Agent Demo

A deliberately simple Gradio chat app for **demonstrating and exploring the [Domains.Kred](https://domains.kred) APIs**.

It is a scratchpad, not a product. Claude Opus 5 is pointed at the live Domains.Kred MCP server (`https://api.domains.kred/mcp`) and you watch, in a side panel, exactly which API tools it calls and what they return. The point is to see the API surface in action — domains, DNS, ENS, agent identity, transparency log — with as little app code in the way as possible.

Built as part of the **NFT.NYC vibesprint series, running August–September 2026**. Details of the vibesprints: <https://NFT.NYC/vibesprint>

## What you can poke at

- Domain availability, pricing, and status
- DNS zone and record management
- ENS name resolution and management
- AI-agent identity records on a domain — AID, ANS, MCP-I, DNSid
- The public Domains.Kred transparency log

Example prompts are wired into the UI:

```
Is agentkred.xyz available, and what would 2 years of registration cost?
Show me the DNS records for kred.domains.
Does kred.domains have an AID or ANS agent-identity record published?
What's the current signed tree head on the transparency log?
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Create a `.env` file:

```
ANTHROPIC_API_KEY=sk-ant-...
DOMAINS_KRED_API_KEY=...        # optional; only if your account requires auth on MCP calls
```

Real environment variables take precedence over `.env`.

Run it:

```bash
.venv/Scripts/python.exe main.py
```

Gradio prints a local URL (default <http://127.0.0.1:7860>).

## Heads up: this talks to the real API

These are live endpoints, not a sandbox. Registration, renewal, transfer, deletion, DNS edits, minting, key creation/revocation, and credit top-ups **spend real money or make real changes**.

Two mitigations are in place, and neither is a guarantee:

- The system prompt tells the assistant to state cost/impact and wait for explicit confirmation before any state-changing tool call.
- The tool panel flags calls whose names match state-changing keywords — but this is *after the fact*. MCP tools execute server-side before the response reaches this code, so the flag reports what already happened; it cannot block anything.

If you're only exploring, use a read-only scoped Domains.Kred API key (see the `permissions` field on `POST /auth/keys`) rather than a full-access one.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | The whole app — MCP wiring, tool-call extraction, Gradio UI |
| `requirements.txt` | Pinned deps (Gradio 6 / Anthropic SDK with the `mcp-client-2025-11-20` beta) |
