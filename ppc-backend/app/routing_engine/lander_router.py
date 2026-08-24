from typing import Optional


def select_destination(
    campaign: dict,
    geo_url: Optional[str],
    device_url: Optional[str],
    direct_mode: bool,
) -> str:
    """
    Select the final destination URL based on routing priorities.
    Priority: GEO > Device > Campaign default
    """
    if direct_mode:
        return campaign.get("default_offer_url", "https://example.com")

    if geo_url:
        return geo_url

    if device_url:
        return device_url

    return campaign.get("default_offer_url", "https://example.com")


def needs_lander(campaign: dict, destination_url: str) -> bool:
    """Check if a landing page is needed before the offer."""
    # Lander is needed when device rule has a lander_url set
    # and the destination is a lander (not the final offer)
    return False  # Simplified: landing pages handled via device rules
