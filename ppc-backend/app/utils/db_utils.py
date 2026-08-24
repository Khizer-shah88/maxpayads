"""Shared MongoDB query helpers."""
from typing import List, Union
from bson import ObjectId
from bson.errors import InvalidId


def campaign_id_variants(campaign_id: str) -> List[Union[str, ObjectId]]:
    """
    Return both string and ObjectId forms of a campaign id.

    Landing pages and offers may store ``campaign_id`` as either type depending
    on when the document was created, so queries must match both.
    """
    if not campaign_id:
        return []
    variants: List[Union[str, ObjectId]] = [campaign_id]
    try:
        oid = ObjectId(campaign_id)
        if oid not in variants:
            variants.append(oid)
    except (InvalidId, TypeError):
        pass
    return variants


def campaign_id_filter(campaign_id: str) -> dict:
    """Mongo filter fragment matching a campaign id in any stored format."""
    variants = campaign_id_variants(campaign_id)
    if not variants:
        return {"campaign_id": campaign_id}
    if len(variants) == 1:
        return {"campaign_id": variants[0]}
    return {"campaign_id": {"$in": variants}}


def normalize_id(value) -> str:
    """Coerce an id field (str or ObjectId) to a comparable string."""
    if value is None:
        return ""
    return str(value)
