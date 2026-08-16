"""Template rendering.

Templates live in the database so wording can change without a deploy. A
placeholder with no supplied value is an error rather than an empty string —
sending "Hi , your  is confirmed" to a customer is worse than not sending.
"""

from __future__ import annotations

import re

from genesis.db import pool

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class TemplateError(RuntimeError):
    pass


async def load_template(business_id: str, key: str) -> str:
    body = await pool.fetchval(
        "select body from message_templates where business_id = $1 and key = $2",
        business_id,
        key,
    )
    if not body:
        raise TemplateError(f"template '{key}' not found")
    return body


def render(body: str, context: dict[str, object]) -> str:
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in context or context[name] is None:
            missing.append(name)
            return ""
        return str(context[name])

    out = PLACEHOLDER.sub(substitute, body)
    if missing:
        raise TemplateError(f"missing template values: {', '.join(sorted(set(missing)))}")
    return out.strip()


async def render_template(business_id: str, key: str, context: dict[str, object]) -> str:
    return render(await load_template(business_id, key), context)
