# ResolveBot

A customer-support chat assistant for the fictional store ShopSphere. One endpoint: `POST /chat` on port 8000.
Customers can track orders, return items, check warranty, cancel orders and ask about policies.

**Design in one line:** Python makes every decision (eligibility, warranty dates, ownership, what may be saved);
Gemini (through LangChain) only chooses which tool to call and explains the result in friendly words.

## Install and run

```bash
python -m venv .venv && source .venv/bin/activate      # Python 3.10+
pip install -r requirements.txt
cp .env.example .env            # add your GEMINI_API_KEY
# put policies.md, manifest.json and shopsphere.db in ./data  (or change the paths in .env)
uvicorn main:app --port 8000    # (uvicorn app.main:app --port 8000 also works)
```

Settings are environment variables (defaults in `.env.example`): `POLICIES_PATH`, `MANIFEST_PATH`, `DB_PATH`,
`APP_TODAY` (default `2026-07-01`; the date the app treats as "today" - the computer clock is never used),
`LLM_PROVIDER` (`gemini`), `GEMINI_API_KEY`, optional `LLM_MODEL` (default `gemini-2.5-flash`),
and tuning parameters `LLM_TIMEOUT` (default `60`), `REPLY_DEADLINE` (default `60`), and `MAX_TOOL_CALLS` (`6`).
The model runs at temperature 0.

Try it:
```bash
curl -s localhost:8000/chat -H 'X-Customer-Id: C1009' -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","message":"Return the speaker from SS-10458, I changed my mind."}'
```

## Project layout (routes -> services -> repositories)

```
main.py                      shim so `uvicorn main:app` works
app/main.py                  creates the FastAPI app
app/routes/chat.py           POST /chat, header and body checks, 400 / 401 / 403
app/schemas/chat.py          the reply shape (answer, route, citations, tool_calls, pending_confirmation)
app/services/
    chat_service.py          the tool loop, propose-then-confirm, builds the reply
    session_service.py       sessions, the waiting proposal, "is this a clear yes?"
    order_service.py         get_orders and the values our code works out
    return_service.py        check_return_eligibility, create_return_request
    ticket_service.py        warranty and cancellation tickets
    policy_service.py        search_policy
    llm_service.py           the Gemini model (LangChain ChatGoogleGenerativeAI)
app/repositories/            SQL only (customers, orders, parameters, return_requests, support_tickets)
app/rules/                   business rules in plain Python (dates, returns, warranty, cancellation, errors)
app/rag/                     LangChain Documents (loader.py) and a BM25 retriever (retriever.py)
app/tools/registry.py        the 5 LangChain StructuredTools Gemini sees
app/prompts/system_prompt.py behaviour rules for the model (no policy facts, no business numbers)
tests/smoke_test.py          optional offline check with a scripted fake Gemini
```

Request flow: route -> `chat_service` -> Gemini asks for a tool -> `tools/registry.py` -> a service ->
repositories (SQL) and rules (decisions).

## How it works

**Where LangChain is used.** `ChatGoogleGenerativeAI` + `bind_tools` (the model), `StructuredTool` with pydantic
input schemas (the five tools), and `Document` + a custom `BaseRetriever` (policy search). The tool loop, the
business rules, the ownership checks and the yes-step are deliberately plain Python so each rule can be pointed to.

**Tool loop.** The message, history and tool list go to Gemini. If it asks for tools, our code runs them and sends the
results back, until it gives a final JSON reply (`route`, `answer`, `citations`). At most 6 tool calls per message
(`MAX_TOOL_CALLS`), then a polite fallback.

**Business rules (`app/rules`).** Every number comes from the `policy_parameters` table.
- Days since delivery = `APP_TODAY` - delivery date; "within 30 days" means 30 or fewer.
- Return checks run in order and stop at the first failure: order/items/delivered -> `NON_RETURNABLE` ->
  `RETURN_WINDOW_EXPIRED` -> `OPENED_NOT_RETURNABLE` (only opened + `changed_mind` + `unopened_only` products).
- Warranty end = delivery date + N months (`relativedelta`, month-end safe); the last day is still covered.
- Cancellation tickets only when the order is `processing`. Warranty tickets only when delivered with an active warranty.

**Security.** The customer id comes only from the `X-Customer-Id` header. Tools are built per request with that id
captured in code, so it is not an input Gemini can set. Every order query filters on `customer_id` in SQL. A missing
order and someone else's order give the same `ORDER_NOT_FOUND`, and the reply is forced to exactly
"I couldn't find that order on your account." (route `no_answer`).

**Policy search.** `app/rag/loader.py` splits `policies.md` at each `# ` title, reads the `Document ID`, and joins each
document to `manifest.json` by `doc_id`. One LangChain `Document` is made per `###` section, with `doc_id` and `section`
as metadata. Only documents with status `current` and `effective_date <= APP_TODAY` are searched as `in_effect`;
superseded ones are never used. Current documents that start later are returned flagged `future_change`, so the
assistant can mention them only as an upcoming change with the start date. Ranking is BM25 (`rank_bm25`) inside a custom
LangChain retriever: no embeddings, no extra API calls, runs on any CPU. FAQ sections rank below policies.
`citations` is built in Python: only sections that `search_policy` really returned in this turn and Gemini says it used.

**The yes-step.** `create_return_request` and `create_support_ticket` never save when Gemini calls them. They only
check the rules and store one waiting proposal in the session (`pending_confirmation: true`, tool status
`pending_confirmation`). If the very next message is a clear yes (decided by a small Python check, not by the LLM), the
service runs the real save, re-checks the rules first, and writes one row. Any other message ("no", "just do it",
changed details) forgets the proposal. The save functions also refuse to run without `confirmed=True`, which only the
yes-path passes.

**Sessions.** Kept in memory by `session_id` (chat history + waiting proposal). A session belongs to the customer who
started it (403 for anyone else).

## Assumptions

- A tool's status is `error` whenever it returns an `error_code` (including a normal "not eligible" from
  `check_return_eligibility`), otherwise `success`.
- A "clear yes" is a short message made only of yes-words ("yes", "yes go ahead", "confirm", "please do", "ok").
  "just do it" and "yes but only the power bank" are not a yes.
- `item_ids` are stored as a JSON list string, e.g. `["SS-10458-1"]`.
- Order ids without the hyphen ("SS10458") are accepted.
- A delivered order whose shipment has no `delivered_at` (or a date after `APP_TODAY`) counts as not delivered.
- An already cancelled order returns an extra code, `ORDER_ALREADY_CANCELLED` (not in the given list).
- `get_orders` returns `INVALID_STATUS` for a bad status filter and lists at most the 30 most recent orders.
- Confirmed actions are answered with a fixed template (not LLM text), so no policy facts are typed into the code.
- Sessions live in memory only and are lost when the service restarts.

## What does not work yet / limits

- **Free-tier API key limitations & latency:** The application was developed and tested using only a free-tier Gemini API key, as a paid API key was not available. Due to free-tier latency and stricter rate limits during multi-turn tool loops, `LLM_TIMEOUT` and `REPLY_DEADLINE` were configured to 60 seconds to prevent early timeout failures. Rapid consecutive requests or traffic bursts can still trigger free-tier rate-limit errors (which return a polite fallback message). If running with a paid API key with higher rate limits and lower latency, these values can safely be dialed down to `LLM_TIMEOUT=20`–`30` and `REPLY_DEADLINE=25`–`35` seconds for faster turnaround.
- Search is keyword-based (BM25): a question worded very differently from the policy text (for example "abroad" for
  "outside India") may miss; Gemini can rephrase its query.
- Whether Gemini correctly tells "asked for the action" from "only asked a question" depends on the prompt and model.
- Duplicate return requests for the same item are not blocked.

## Example chats

Replace or extend these with real transcripts from your own run before you submit.

Verified with the scripted fake model (`tests/smoke_test.py`), customer `C1009`:
1. "Return the speaker from SS10458, I changed my mind." -> `pending_confirmation: true`, nothing saved.
   "Yes, go ahead." -> `create_return_request` status `success`, one row in `return_requests`.
2. "Please return it." then "just do it" / "no" -> nothing saved, proposal forgotten.
3. "Where is SS-99999?" or another customer's order -> "I couldn't find that order on your account." (`no_answer`).
4. Cancel a shipped order -> `ORDER_ALREADY_SHIPPED`, no proposal. Cancel a `processing` order -> proposal, then
   "confirm" saves one open ticket.

## Where I used AI coding assistants

This code was generated and refined using Claude (Anthropic) and Antigravity from the assignment specifications and tested with `tests/smoke_test.py`. I have reviewed the implementation and can explain each file and architectural decision.
