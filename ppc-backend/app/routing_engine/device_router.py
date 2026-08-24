from typing import Optional


async def route_by_device(campaign_id: str, device_type: str, os_name: Optional[str], db) -> Optional[str]:
    """
    Match visitor device/OS against campaign device rules.
    Returns lander URL or offer URL, or None if no match.
    """
    # Try OS-specific match first
    if os_name:
        rule = await db.device_rules.find_one(
            {
                "campaign_id": campaign_id,
                "device_type": device_type,
                "os": os_name,
            },
            sort=[("priority", -1)],
        )
        if rule:
            return rule.get("lander_url") or rule.get("offer_url")

    # Fallback: device type only match
    rule = await db.device_rules.find_one(
        {
            "campaign_id": campaign_id,
            "device_type": device_type,
            "$or": [{"os": None}, {"os": {"$exists": False}}, {"os": ""}],
        },
        sort=[("priority", -1)],
    )
    if rule:
        return rule.get("lander_url") or rule.get("offer_url")

    return None


async def get_device_rules_for_campaign(campaign_id: str, db) -> list:
    cursor = db.device_rules.find({"campaign_id": campaign_id}).sort("priority", -1)
    rules = await cursor.to_list(length=None)
    for r in rules:
        r["id"] = str(r.pop("_id", ""))
    return rules
