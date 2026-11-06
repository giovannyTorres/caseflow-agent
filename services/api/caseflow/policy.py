"""Versioned original simulator policy; never an external banking policy."""


def current_policy() -> dict:
    return {'id': 'juniper-policy-v1', 'version': 1, 'text': 'Duplicate settled charges may be reimbursed once after supervisor approval. Missing evidence requires an evidence request. Confirmed legitimate purchases are rejected. Never exceed the disputed amount.'}
