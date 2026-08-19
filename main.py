import json
import os
import gradio as gr
import anthropic
from dotenv import load_dotenv

# Must run before anything below reads the environment — the client and
# DOMAINS_KRED_API_KEY are both resolved at import time. Real environment
# variables take precedence over .env, so an exported key still wins.
load_dotenv()

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

MCP_SERVER_URL = "https://api.domains.kred/mcp"
MCP_SERVER_NAME = "domains-kred"
# If your domains.kred account needs auth on MCP calls, set this. Ideally use
# a key scoped to read-only permissions for this demo (see POST /auth/keys'
# `permissions` field) rather than a full-access key.
DOMAINS_KRED_API_KEY = os.environ.get("DOMAINS_KRED_API_KEY")

# Purely informational — MCP tool calls execute server-side before the
# response reaches this code, so this cannot block anything. It only flags
# what already happened, for the human watching the demo.
RISKY_KEYWORDS = ("register", "renew", "transfer", "delete", "revoke",
                   "topup", "mint", "modify", "create_key", "recharge")

# A long server-side tool run can stop with `pause_turn`; we resume it, but cap
# the resumes so a misbehaving server can't hang the UI indefinitely.
MAX_PAUSE_CONTINUATIONS = 5

SYSTEM_PROMPT = """You are a demo assistant for Domains.Kred, a domain registrar \
and DNS provider that also issues verifiable identity credentials for AI agents \
(AID, ANS, MCP-I, DNSid) and publishes a public transparency log of its operations.

You can: check domain availability/price/status, manage DNS zones and records, \
resolve and manage ENS names, provision or inspect an AI agent's identity records \
on a domain (AID/ANS/MCP-I/DNSid), and look up entries in the public transparency log.

Any action that spends credits, spends money, or changes a real record — \
registering, renewing, transferring, or deleting a domain; minting a token; \
creating or revoking API keys or agent credentials; modifying DNS; topping up \
credits — is irreversible or costs real money. Before calling any tool that does \
one of these, state plainly what you're about to do and its cost/impact, and wait \
for the user to explicitly confirm in their next message. Never take that action \
on an ambiguous or implied request. Read-only lookups (availability, price, \
status, records, transparency log) need no confirmation."""

def _mcp_server_entry():
    entry = {"type": "url", "name": MCP_SERVER_NAME, "url": MCP_SERVER_URL}
    if DOMAINS_KRED_API_KEY:
        entry["authorization_token"] = DOMAINS_KRED_API_KEY
    return entry

def call_claude_with_mcp(messages):
    kwargs = dict(
        model="claude-opus-5",
        # Thinking is on by default on Opus 5, and max_tokens caps thinking plus
        # response text together — too tight a budget truncates the visible answer.
        max_tokens=16000,
        betas=["mcp-client-2025-11-20"],
        system=SYSTEM_PROMPT,
        mcp_servers=[_mcp_server_entry()],
        tools=[{"type": "mcp_toolset", "mcp_server_name": MCP_SERVER_NAME}],
    )
    response = client.beta.messages.create(messages=messages, **kwargs)
    for _ in range(MAX_PAUSE_CONTINUATIONS):
        if response.stop_reason != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": response.content}]
        response = client.beta.messages.create(messages=messages, **kwargs)
    return response

def _plain(content):
    """An mcp_tool_result's content is a str or a list of SDK block objects, which
    json.dumps can't serialize. Convert the blocks to plain dicts."""
    if isinstance(content, str):
        return content
    return [b.model_dump(mode="json") if hasattr(b, "model_dump") else b
            for b in (content or [])]

def _refusal_notice(response):
    """Opus 5's safety classifiers can decline a request: the call still returns
    HTTP 200, with stop_reason 'refusal' and content that is either empty or cut
    off mid-answer. stop_details can be absent even on a refusal, so read it
    defensively rather than branching on it."""
    details = getattr(response, "stop_details", None)
    category = getattr(details, "category", None)
    explanation = getattr(details, "explanation", None)
    note = "_Claude declined this request"
    if category:
        note += " (category: %s)" % category
    note += "._"
    if explanation:
        note += "\n\n_%s_" % explanation
    return note

def extract_reply_and_tools(response):
    reply_parts, tool_calls = [], []
    for block in response.content:
        if block.type == "text":
            reply_parts.append(block.text)
        elif block.type == "mcp_tool_use":
            risky = any(k in block.name.lower() for k in RISKY_KEYWORDS)
            tool_calls.append({"tool": block.name, "input": block.input, "risky": risky})
        elif block.type == "mcp_tool_result":
            tool_calls.append({
                "result": _plain(block.content),
                "is_error": block.is_error,
            })
    return "\n".join(reply_parts).strip(), tool_calls

def respond(user_message, chat_history):
    claude_messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]
    claude_messages.append({"role": "user", "content": user_message})

    response = call_claude_with_mcp(claude_messages)
    reply_text, tool_calls = extract_reply_and_tools(response)

    if response.stop_reason == "refusal":
        reply_text = (reply_text + "\n\n" + _refusal_notice(response)).strip()
    elif response.stop_reason == "pause_turn":
        reply_text = (reply_text + "\n\n_(Still paused after %d server-side "
                      "continuations — stopped here.)_" % MAX_PAUSE_CONTINUATIONS).strip()

    chat_history = chat_history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply_text},
    ]

    banner = "⚠️  A tool call this turn looked state-changing or costly — check it below.\n\n" \
        if any(t.get("risky") for t in tool_calls) else ""
    tool_panel = banner + (json.dumps(tool_calls, indent=2) if tool_calls else "No MCP tools were called for this turn.")
    return chat_history, tool_panel, ""

EXAMPLE_QUERIES = [
    "Is agentkred.xyz available, and what would 2 years of registration cost?",
    "Show me the DNS records for kred.domains.",
    "Does kred.domains have an AID or ANS agent-identity record published?",
    "What's the current signed tree head on the transparency log?",
]

with gr.Blocks(title="Domains.Kred Agent Demo") as demo:
    gr.Markdown(
        "# Domains.Kred — MCP Agent Demo\n"
        "Ask about domain registration, DNS/ENS, or AI-agent identity (AID / ANS / MCP-I / DNSid) "
        "and watch Claude call the real Domains.Kred MCP server.\n\n"
        "**Note:** registration, renewal, and credit top-ups spend real credits or money and are hard to reverse."
        "Transfer, deletion, DNS edits are permanaent changes and hard to reverse. The assistant is instructed to confirm "
        "before doing any of those — treat that as a demo safeguard, not a guarantee."
    )
    with gr.Row():
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(height=500)
            msg = gr.Textbox(label="Ask something", placeholder=EXAMPLE_QUERIES[0])
            gr.Examples(examples=EXAMPLE_QUERIES, inputs=msg)
            clear = gr.Button("Clear")
        with gr.Column(scale=1):
            gr.Markdown("### MCP tool calls (this turn)")
            tool_panel = gr.Code(language="json")

    msg.submit(respond, [msg, chatbot], [chatbot, tool_panel, msg])
    clear.click(lambda: ([], "", ""), None, [chatbot, tool_panel, msg])

if __name__ == "__main__":
    demo.launch()