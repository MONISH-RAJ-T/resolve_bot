"""The five tools, as LangChain StructuredTools. Gemini reads these names, descriptions and inputs.
Tools are built per request, so the customer id always comes from the X-Customer-Id header (closure) and
is never an input the LLM can set. The two write tools only PROPOSE: the real save happens after the customer's yes."""
from typing import Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.services import order_service, policy_service, return_service

WRITE_TOOLS = {"create_return_request", "create_support_ticket"}


class GetOrdersInput(BaseModel):
    order_id: str | None = Field(default=None, description="Order ID such as SS-10458. Leave empty to list orders.")
    status: str | None = Field(default=None, description="Optional filter: processing, shipped, delivered or cancelled.")


class SearchPolicyInput(BaseModel):
    query: str = Field(description="Short search words, for example 'return window days'.")


class ReturnInput(BaseModel):
    order_id: str = Field(description="Order ID such as SS-10458.")
    item_ids: list[str] = Field(description="Item IDs such as SS-10458-1 (taken from get_orders).")
    reason: str = Field(description="'changed_mind' (customer just does not want it) or "
                                    "'defective' (broken, damaged or wrong item).")


class TicketInput(BaseModel):
    order_id: str = Field(description="Order ID such as SS-10458.")
    ticket_type: str = Field(description="'warranty' (fault, item under warranty) or "
                                         "'cancellation' (cancel an order that has not shipped).")
    summary: str = Field(description="One sentence describing the problem or request.")


def build_tools(customer_id: str, propose: Callable[[str, dict], dict]) -> list[StructuredTool]:
    """propose(tool_name, args) records a proposal and returns a result dict; it never writes to the database."""
    return [
        StructuredTool.from_function(
            name="get_orders", args_schema=GetOrdersInput,
            description="Look up this customer's orders: status, items (item_id, opened flag), shipment and ETA, "
                        "delivery date, days since delivery, and each item's warranty end date and whether the warranty "
                        "is active. Pass order_id for one order, status to filter, or nothing to list recent orders. "
                        "Use it first for tracking, warranty, return and cancellation questions.",
            func=lambda order_id=None, status=None: order_service.get_orders(customer_id, order_id, status)),
        StructuredTool.from_function(
            name="search_policy", args_schema=SearchPolicyInput,
            description="Search the store's policy documents. Returns the best matching paragraphs with doc_id and "
                        "section. Use it for any policy question, and also to find the section you cite when you "
                        "explain a return, warranty, cancellation or shipping answer.",
            func=lambda query: policy_service.search_policy(query)),
        StructuredTool.from_function(
            name="check_return_eligibility", args_schema=ReturnInput,
            description="Check whether items can be returned. Returns result 'eligible' or an error_code that says "
                        "why not. Always use it for return questions - never decide yourself.",
            func=lambda order_id, item_ids, reason: return_service.check_return_eligibility(
                customer_id, order_id, item_ids, reason)),
        StructuredTool.from_function(
            name="create_return_request", args_schema=ReturnInput,
            description="Propose a return request. Call it ONLY when the customer asked you to return the items "
                        "(not when they only ask whether they can) and check_return_eligibility said eligible. "
                        "It does NOT save anything: the customer must say yes in their next message first.",
            func=lambda order_id, item_ids, reason: propose(
                "create_return_request", {"order_id": order_id, "item_ids": item_ids, "reason": reason})),
        StructuredTool.from_function(
            name="create_support_ticket", args_schema=TicketInput,
            description="Propose a support ticket: 'warranty' or 'cancellation'. Call it ONLY when the customer asked "
                        "for it. It does NOT save anything: the customer must say yes in their next message first.",
            func=lambda order_id, ticket_type, summary: propose(
                "create_support_ticket", {"order_id": order_id, "ticket_type": ticket_type, "summary": summary})),
    ]
