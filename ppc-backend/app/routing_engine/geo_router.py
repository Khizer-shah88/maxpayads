from typing import Optional


async def route_by_geo(campaign_id: str, country_code: Optional[str], db) -> Optional[str]:
    """
    Match visitor country against campaign GEO rules.
    Returns offer URL or None if no match.
    """
    if not country_code:
        return None

    rule = await db.geo_rules.find_one(
        {"campaign_id": campaign_id, "country_code": country_code.upper()},
        sort=[("priority", -1)],
    )
    return rule["offer_url"] if rule else None


async def get_geo_rules_for_campaign(campaign_id: str, db) -> list:
    cursor = db.geo_rules.find({"campaign_id": campaign_id}).sort("priority", -1)
    rules = await cursor.to_list(length=None)
    for r in rules:
        r["id"] = str(r.pop("_id", ""))
    return rules
