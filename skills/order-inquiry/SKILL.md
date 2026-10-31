---
name: order-inquiry
description: Look up order status by product name or keyword and present results to the customer
allowed-tools: checkOrderStatus
---

# Order Inquiry

You help customers check the status of their orders.

## Procedure

1. Use `checkOrderStatus` with the product name or keyword the customer provides.
2. If the tool returns **multiple matches**, present the list and ask the customer which product they mean.
3. If the tool returns **a single match**, present the status with context from the order-statuses reference.
4. Always use the **canonical product name** returned by the tool for any follow-up operations (tickets, escalations).
5. Never guess delivery dates, ETAs, or tracking numbers — only report what the tool returns.
