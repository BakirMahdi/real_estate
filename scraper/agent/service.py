"""Orchestrates one agent conversation turn: load history, call Gemini, persist."""

from datetime import datetime, timezone

from ..ml.estimator import ModelNotTrained, estimate_property
from ..queries import get_property_by_id
from . import conversation_store
from .gemini_client import generate_reply


def _property_context_text(property_id: int) -> str | None:
    prop = get_property_by_id(property_id)
    if not prop:
        return None

    lines = [
        f"Titre: {prop['title']}",
        f"Type: {prop['property_type']} / {prop.get('subcategory') or '-'}",
        f"Transaction: {prop['listing_type']}",
        f"Prix affiche: {prop['price']} TND",
        f"Surface: {prop['area']} m2" if prop.get("area") else "Surface: inconnue",
        f"Localisation: {prop.get('governorate') or prop.get('city') or '-'}",
    ]
    try:
        estimate = estimate_property(prop)
        lines.append(f"Estimation IA: {estimate['estimated_price']} TND")
        if estimate["investment_score"] is not None:
            lines.append(f"Score d'investissement: {estimate['investment_score']}/100")
    except ModelNotTrained:
        pass

    return "\n".join(lines)


def chat(user_id: int, user_message: str, property_id: int | None = None) -> str:
    history = conversation_store.load_messages(user_id)
    context = _property_context_text(property_id) if property_id is not None else None

    reply = generate_reply(history, user_message, property_context=context)

    now = datetime.now(timezone.utc).isoformat()
    conversation_store.append_messages(
        user_id,
        [
            {"role": "user", "content": user_message, "created_at": now},
            {"role": "model", "content": reply, "created_at": now},
        ],
    )
    return reply
