from app.utils.ua_parser import parse_user_agent, is_bot_user_agent


async def get_device_info(user_agent: str) -> dict:
    """Parse user agent and return device information."""
    return parse_user_agent(user_agent)


async def check_is_bot(user_agent: str) -> bool:
    """Check if the user agent is a bot."""
    return is_bot_user_agent(user_agent)
