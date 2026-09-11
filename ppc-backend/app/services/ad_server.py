from typing import Optional
from app.services.campaign_service import get_all_campaigns, select_weighted_campaign
import logging

logger = logging.getLogger(__name__)


async def serve_ad_js(publisher_id: str, website_id: str, base_url: str, db, redis, ad_type: str = "banner") -> str:
    """Generate JavaScript ad code for a publisher's website."""
    campaigns = await get_all_campaigns(db, redis, include_rules=False)
    active = [c for c in campaigns if c.get("status") == "active"]

    if not active:
        return _empty_ad_js()

    campaign = select_weighted_campaign(active)
    if not campaign:
        return _empty_ad_js()

    click_url = f"{base_url}?pub={publisher_id}&site={website_id}"

    # The embed code served on the Websites page carries PUBLIC ids
    # (PUB_XXX / SITE_XXX), but ad_settings documents are keyed by the
    # INTERNAL ids. Resolve public → internal before the lookup so saved
    # customizations apply regardless of which embed code the publisher used.
    settings_publisher_id = publisher_id
    settings_website_id = website_id
    try:
        from app.utils.public_id_utils import (
            resolve_publisher_id, resolve_website_id,
        )
        if publisher_id:
            resolved_pub = await resolve_publisher_id(db, publisher_id)
            if resolved_pub:
                settings_publisher_id = resolved_pub
        if website_id:
            resolved_site = await resolve_website_id(db, website_id)
            if resolved_site:
                settings_website_id = resolved_site
    except Exception as e:
        logger.debug(f"Public id resolution failed in ad server: {e}")

    # Load custom ad settings from DB if available
    settings = await db.ad_settings.find_one({
        "website_id": settings_website_id,
        "publisher_id": settings_publisher_id,
    })
    if not settings:
        settings = {}

    if ad_type == "button":
        return _button_ad_js(click_url, website_id, settings)
    elif ad_type == "popup":
        return _popup_ad_js(click_url, website_id, settings)
    elif ad_type == "video":
        return _video_ad_js(click_url, website_id, settings)
    else:
        return _banner_ad_js(click_url, website_id, settings)


def _banner_ad_js(click_url: str, website_id: str, s: dict) -> str:
    bg = s.get("bg_color", "#000000")
    accent = s.get("button_color", "#5465FF")
    text_color = s.get("text_color", "#FFFFFF")
    text = s.get("banner_text", "Advertisement")
    font_size = s.get("font_size", "16")
    radius = s.get("border_radius", "8")
    w = s.get("banner_width", "728")
    h = s.get("banner_height", "90")

    return f"""(function(){{
  var c=document.createElement('div');
  c.id='ppc-ad-{website_id}';
  c.style.cssText='max-width:{w}px;height:{h}px;margin:10px auto;overflow:hidden;';
  var a=document.createElement('a');
  a.href='{click_url}';a.target='_blank';a.rel='noopener noreferrer';
  a.style.cssText='display:flex;align-items:center;justify-content:center;width:100%;height:100%;background:linear-gradient(135deg,{bg},{accent});border-radius:{radius}px;text-decoration:none;font-family:sans-serif;';
  var t=document.createElement('span');
  t.textContent='{text}';
  t.style.cssText='color:{text_color};font-weight:bold;font-size:{font_size}px;';
  a.appendChild(t);c.appendChild(a);
  var scripts=document.getElementsByTagName('script');
  var cs=scripts[scripts.length-1];
  cs.parentNode.insertBefore(c,cs.nextSibling);
}})();"""


def _button_ad_js(click_url: str, website_id: str, s: dict) -> str:
    btn_color = s.get("button_color", "#5465FF")
    btn_text_color = s.get("button_text_color", "#FFFFFF")
    btn_text = s.get("button_text", "Download Now")
    font_size = s.get("font_size", "16")
    radius = s.get("border_radius", "8")

    return f"""(function(){{
  var c=document.createElement('div');
  c.id='ppc-ad-{website_id}';
  c.style.cssText='text-align:center;margin:10px auto;';
  var a=document.createElement('a');
  a.href='{click_url}';a.target='_blank';a.rel='noopener noreferrer';
  a.style.cssText='display:inline-block;background:{btn_color};color:{btn_text_color};padding:15px 32px;text-align:center;text-decoration:none;font-size:{font_size}px;font-weight:bold;margin:4px 2px;cursor:pointer;border-radius:{radius}px;transition:0.3s;font-family:sans-serif;';
  a.textContent='{btn_text}';
  a.onmouseover=function(){{this.style.opacity='0.85';this.style.boxShadow='0 12px 16px rgba(0,0,0,0.24)';}};
  a.onmouseout=function(){{this.style.opacity='1';this.style.boxShadow='none';}};
  c.appendChild(a);
  var scripts=document.getElementsByTagName('script');
  var cs=scripts[scripts.length-1];
  cs.parentNode.insertBefore(c,cs.nextSibling);
}})();"""


def _popup_ad_js(click_url: str, website_id: str, s: dict) -> str:
    bg = s.get("bg_color", "#000000")
    text_color = s.get("text_color", "#FFFFFF")
    btn_color = s.get("button_color", "#5465FF")
    btn_text_color = s.get("button_text_color", "#FFFFFF")
    title = s.get("popup_title", "Special Offer!")
    msg = s.get("popup_message", "Click here for an exclusive deal")
    btn_text = s.get("button_text", "Claim Now")
    delay = s.get("popup_delay", 3)
    font_size = s.get("font_size", "16")
    radius = s.get("border_radius", "8")

    return f"""(function(){{
  setTimeout(function(){{
    var ov=document.createElement('div');
    ov.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:99999;display:flex;align-items:center;justify-content:center;';
    var bx=document.createElement('div');
    bx.style.cssText='background:{bg};border-radius:{radius}px;padding:30px 40px;max-width:420px;width:90%;text-align:center;position:relative;box-shadow:0 20px 60px rgba(0,0,0,0.3);';
    var cl=document.createElement('span');
    cl.textContent='\\u00D7';cl.style.cssText='position:absolute;top:10px;right:15px;font-size:24px;cursor:pointer;color:{text_color};opacity:0.7;';
    cl.onclick=function(){{ov.remove();}};
    var t=document.createElement('h3');
    t.textContent='{title}';t.style.cssText='color:{text_color};margin:0 0 10px;font-size:22px;font-family:sans-serif;';
    var m=document.createElement('p');
    m.textContent='{msg}';m.style.cssText='color:{text_color};opacity:0.8;margin:0 0 20px;font-size:14px;font-family:sans-serif;';
    var b=document.createElement('a');
    b.href='{click_url}';b.target='_blank';b.rel='noopener noreferrer';
    b.textContent='{btn_text}';b.style.cssText='display:inline-block;background:{btn_color};color:{btn_text_color};padding:12px 30px;border-radius:{radius}px;text-decoration:none;font-weight:bold;font-size:{font_size}px;font-family:sans-serif;';
    bx.appendChild(cl);bx.appendChild(t);bx.appendChild(m);bx.appendChild(b);
    ov.appendChild(bx);document.body.appendChild(ov);
    ov.addEventListener('click',function(e){{if(e.target===ov)ov.remove();}});
  }},{delay * 1000});
}})();"""


def _video_ad_js(click_url: str, website_id: str, s: dict) -> str:
    bg = s.get("bg_color", "#000000")
    text_color = s.get("text_color", "#FFFFFF")
    btn_color = s.get("button_color", "#5465FF")
    btn_text_color = s.get("button_text_color", "#FFFFFF")
    vid_text = s.get("video_placeholder_text", "Watch Now")
    font_size = s.get("font_size", "16")
    radius = s.get("border_radius", "8")

    return f"""(function(){{
  var c=document.createElement('div');
  c.id='ppc-ad-{website_id}';
  c.style.cssText='max-width:480px;margin:10px auto;background:{bg};border-radius:{radius}px;overflow:hidden;font-family:sans-serif;';
  var a=document.createElement('a');
  a.href='{click_url}';a.target='_blank';a.rel='noopener noreferrer';
  a.style.cssText='display:block;text-decoration:none;';
  var vp=document.createElement('div');
  vp.style.cssText='aspect-ratio:16/9;background:linear-gradient(135deg,{bg},{btn_color});display:flex;align-items:center;justify-content:center;';
  var pb=document.createElement('div');
  pb.style.cssText='width:64px;height:64px;background:rgba(255,255,255,0.9);border-radius:50%;display:flex;align-items:center;justify-content:center;';
  var tri=document.createElement('div');
  tri.style.cssText='width:0;height:0;border-top:14px solid transparent;border-bottom:14px solid transparent;border-left:22px solid {btn_color};margin-left:4px;';
  pb.appendChild(tri);vp.appendChild(pb);a.appendChild(vp);
  var bar=document.createElement('div');
  bar.style.cssText='padding:12px 16px;display:flex;align-items:center;justify-content:space-between;';
  var lbl=document.createElement('span');
  lbl.textContent='{vid_text}';lbl.style.cssText='color:{text_color};font-weight:bold;font-size:{font_size}px;';
  var btn=document.createElement('span');
  btn.textContent='Play';btn.style.cssText='background:{btn_color};color:{btn_text_color};padding:6px 16px;border-radius:{radius}px;font-size:13px;font-weight:bold;';
  bar.appendChild(lbl);bar.appendChild(btn);a.appendChild(bar);
  c.appendChild(a);
  var scripts=document.getElementsByTagName('script');
  var cs=scripts[scripts.length-1];
  cs.parentNode.insertBefore(c,cs.nextSibling);
}})();"""


def _empty_ad_js() -> str:
    return "/* No active campaigns */"


async def get_redirect_url(publisher_id: str, website_id: Optional[str], request_data: dict, db, redis) -> str:
    """Determine the final redirect URL for a click."""
    from app.services.traffic_router import route_click
    return await route_click(
        {
            "publisher_id": publisher_id,
            "website_id": website_id,
            **request_data,
        },
        db,
        redis,
    ) # type: ignore
