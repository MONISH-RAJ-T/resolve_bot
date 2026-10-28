"""The chat brain: the tool loop, the propose-then-confirm step, and building the reply.
Python decides everything; Gemini only picks tools and words the answer."""
import json
import re
import time
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.core import config
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.rules import dates
from app.rules.errors import NOT_FOUND_TEXT, err
from app.schemas.chat import ChatReply, Citation, ToolCallLog
from app.services import llm_service, return_service, ticket_service
from app.services.session_service import Session, get_session, is_yes
from app.tools.registry import WRITE_TOOLS, build_tools

ROUTES = ("answer", "clarify", "no_answer", "out_of_scope")
REASON_TEXT = {"changed_mind": "change of mind", "defective": "defective, damaged or wrong item"}


def _reply(answer, route, citations, tool_calls, pending) -> ChatReply:
    return ChatReply(request_id=str(uuid.uuid4()), answer=answer, route=route,
                     citations=[Citation(**c) for c in citations],
                     tool_calls=[ToolCallLog(**t) for t in tool_calls], pending_confirmation=pending)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in content if isinstance(p, (str, dict)))
    return str(content or "")


def _parse_final(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        if isinstance(data, dict) and "answer" in data:
            return data
    except ValueError:
        pass
    return {"route": "answer", "answer": text or "Sorry, I could not put together a reply.", "citations": []}


def _status(result: dict) -> str:
    if result.get("status") == "pending_confirmation":
        return "pending_confirmation"
    return "error" if "error_code" in result else "success"


# ------------------------------------------------------------------ step 1: propose (never saves)
def _propose(sess: Session, customer_id: str, name: str, args: dict) -> dict:
    """Checks the rules and remembers the request as the one waiting proposal."""
    if name == "create_return_request":
        check = return_service.check_return_eligibility(customer_id, args.get("order_id"),
                                                        args.get("item_ids"), args.get("reason"))
        if "error_code" in check:
            return check
        clean = {"order_id": check["order_id"], "item_ids": check["item_ids"], "reason": check["reason"]}
    else:
        check = ticket_service.check_ticket_allowed(customer_id, args.get("order_id"), args.get("ticket_type"))
        if "error_code" in check:
            return check
        clean = {"order_id": check["order_id"], "ticket_type": check["ticket_type"], "summary": args.get("summary", "")}
    if sess.pending:
        return err("ONE_PROPOSAL_AT_A_TIME",
                   "Another action is already waiting for the customer's yes. Say this one can be done afterwards.")
    sess.pending = {"name": name, "args": clean}
    return {"status": "pending_confirmation",
            "message": "NOTHING IS SAVED YET. Describe exactly what you will do and ask 'Shall I go ahead?'"}


# ------------------------------------------------------------------ step 2: do it (after a clear yes)
def _confirm(sess: Session, customer_id: str) -> ChatReply:
    p, sess.pending = sess.pending, None
    fn = return_service.create_return_request if p["name"] == "create_return_request" else ticket_service.create_support_ticket
    result = fn(customer_id, **p["args"], confirmed=True)  # the service re-checks the rules before saving
    call = {"name": p["name"], "args": p["args"], "status": "error" if "error_code" in result else "success"}
    if "error_code" in result:
        answer = f"I couldn't complete that: {result['message']} Nothing has been saved."
    elif p["name"] == "create_return_request":
        answer = (f"Done. I've created return request {result['request_id']} for {', '.join(result['item_names'])} "
                  f"from order {result['order_id']} (reason: {REASON_TEXT[result['reason']]}).")
    else:
        answer = (f"Done. I've opened a {result['ticket_type']} ticket ({result['ticket_id']}) for order "
                  f"{result['order_id']}. Our team will follow up with you.")
    return _reply(answer, "answer", [], [call], False)


# ------------------------------------------------------------------ the LLM turn (the tool loop)
def _run_llm(sess: Session, customer_id: str, message: str) -> ChatReply:
    tools = build_tools(customer_id, lambda name, args: _propose(sess, customer_id, name, args))
    by_name = {t.name: t for t in tools}
    model = llm_service.build_model(tools)

    messages = [SystemMessage(SYSTEM_PROMPT.replace("{today}", dates.today().strftime("%d %B %Y").lstrip("0")))]
    for m in sess.history[-20:]:
        messages.append(HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"]))
    messages.append(HumanMessage(message))

    log, seen_sections, not_found, calls_made, started = [], set(), False, 0, time.monotonic()
    while True:
        ai = model.invoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            final_text = _text(ai.content)
            break
        if calls_made + len(ai.tool_calls) > config.MAX_TOOL_CALLS or time.monotonic() - started > config.REPLY_DEADLINE:
            sess.pending = None
            return _reply("Sorry, I couldn't finish that in one go. Could you try again with one request at a time?",
                          "answer", [], log, False)
        for call in ai.tool_calls:
            calls_made += 1
            tool = by_name.get(call["name"])
            if tool is None:
                result = err("UNKNOWN_TOOL", f"No tool named {call['name']}")
            else:
                try:
                    result = tool.invoke(call["args"])
                except Exception as exc:  # bad arguments from the LLM must not crash the request
                    result = err("INVALID_ARGUMENTS", f"Could not run {call['name']}: {str(exc)[:200]}")
            if result.get("error_code") == "ORDER_NOT_FOUND":
                not_found = True
            if call["name"] == "search_policy":
                seen_sections.update((r["doc_id"], r["section"]) for r in result.get("results", []))
            log.append({"name": call["name"], "args": call["args"], "status": _status(result)})
            messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False, default=str),
                                        tool_call_id=call["id"], name=call["name"]))

    data = _parse_final(final_text)
    route = data.get("route") if data.get("route") in ROUTES else "answer"
    answer = str(data.get("answer", "")).strip()
    citations, used = [], set()
    for c in data.get("citations") or []:
        key = (c.get("doc_id"), c.get("section")) if isinstance(c, dict) else None
        if key in seen_sections and key not in used:  # only sections that search_policy really returned
            used.add(key)
            citations.append({"doc_id": key[0], "section": key[1]})

    if not_found:  # the same words every time, so nobody can tell "missing" from "someone else's"
        sess.pending = None
        return _reply(NOT_FOUND_TEXT, "no_answer", [], log, False)
    if sess.pending:  # a proposal is waiting for the customer's yes
        if "?" not in answer:
            answer += " Shall I go ahead?"
        return _reply(answer, "answer", citations, log, True)
    if route == "out_of_scope":
        return _reply(answer, route, [], [], False)
    if route == "no_answer":
        citations = []
    return _reply(answer, route, citations, log, False)


# ------------------------------------------------------------------ entry point
def handle(customer_id: str, session_id: str, message: str) -> ChatReply:
    sess = get_session(session_id, customer_id)  # raises PermissionError -> the route answers 403
    with sess.lock:
        try:
            if sess.pending and is_yes(message):
                reply = _confirm(sess, customer_id)
            else:
                sess.pending = None  # anything but a clear yes forgets the proposal
                reply = _run_llm(sess, customer_id, message)
        except Exception as exc:  # LLM down, bad key, ... never crash the endpoint
            print(f"[chat error] {type(exc).__name__}: {exc}")
            sess.pending = None
            reply = _reply("Sorry, I'm having trouble right now. Please try again in a moment.", "answer", [], [], False)
        sess.history += [{"role": "user", "content": message}, {"role": "assistant", "content": reply.answer}]
        return reply
