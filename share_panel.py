"""
DRIVE v1.2.0 - Sharing panel.

Three deliverables (Phase 5):
  1. A compact text report — pasteable to Twitter/Reddit/Discord.
  2. An SVG card — vector, embeds all numbers, loads instantly.
  3. A 1200x630 PNG card — Twitter-card sized, branded, ready to share.
"""
from __future__ import annotations

import datetime as _dt
import io
import html
import os
import sys
from typing import Any, Dict, Optional


GUMROAD_URL = "https://diegoevillarroel.gumroad.com/l/ai-drive-smooth"
TWITTER_URL = "https://twitter.com/intent/tweet?text={text}"


def _format_bytes(n: float) -> str:
    if n is None:
        return "—"
    if n < 1024:
        return f"{n:.0f} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def _framework_names(scan: Dict[str, Any]) -> str:
    names = [f["name"] for f in scan.get("frameworks", []) if f.get("name")]
    if not names:
        return "(none detected)"
    return ", ".join(names[:5]) + (" +" + str(len(names) - 5) + " more" if len(names) > 5 else "")


def build_share_report(scan: Dict[str, Any], shield: Optional[Any]) -> str:
    """Compact plaintext report for Twitter/Reddit/Discord."""
    drive = scan.get("drive", {})
    today = _dt.date.today().isoformat()
    health = drive.get("health_percent")
    health_str = f"{health}%" if isinstance(health, (int, float)) else "unreadable"
    months = drive.get("projected_life_months")
    months_str = f"{months} months" if isinstance(months, (int, float)) else "—"
    shield_msg = (shield.state if shield is not None else "not_attempted")
    if shield_msg == "active":
        shield_msg = "Shield Active"
    elif shield_msg == "not_attempted":
        shield_msg = "Shield not yet activated"
    else:
        shield_msg = f"Shield: {shield_msg}"

    tw_text = (
        f"DRIVE scan — {today}\n"
        f"SSD: {drive.get('model', 'unknown')}\n"
        f"Health: {health_str}\n"
        f"Est. life at current AI load: {months_str}\n"
        f"AI frameworks detected: {_framework_names(scan)}\n"
        f"Est. daily writes: {scan.get('total_daily_gb', 0)} GB/day\n"
        f"{shield_msg}\n"
        f"Get DRIVE: {GUMROAD_URL}"
    )
    return tw_text


def build_share_card_svg(scan: Dict[str, Any], shield: Optional[Any]) -> str:
    """SVG card — vector, used as fallback and as a clipboard target."""
    drive = scan.get("drive", {})
    health = drive.get("health_percent")
    health_str = f"{int(health)}%" if isinstance(health, (int, float)) else "—"
    months = drive.get("projected_life_months") or "—"
    daily = scan.get("total_daily_gb", 0)
    fws = ", ".join(sorted({f["name"] for f in scan.get("frameworks", []) if f.get("name")}))[:80]
    if not fws:
        fws = "(no AI frameworks detected)"
    shield_state = (shield.state if shield is not None else "not_attempted")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
<defs>
  <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
    <stop offset="0%" stop-color="#0a0a0b"/>
    <stop offset="100%" stop-color="#14141a"/>
  </linearGradient>
</defs>
<rect width="1200" height="630" fill="url(#bg)"/>
<rect x="48" y="48" width="160" height="60" fill="#00d4aa" rx="10"/>
<text x="128" y="88" text-anchor="middle" fill="#0a0a0b" font-family="monospace" font-size="36" font-weight="700">DRIVE</text>
<text x="234" y="88" fill="#8888a0" font-family="monospace" font-size="18">// AI SSD Guardian</text>
<text x="48" y="170" fill="#ffffff" font-family="monospace" font-size="40" font-weight="700">{html.escape(str(drive.get("model", "?")))}</text>
<text x="48" y="210" fill="#8888a0" font-family="monospace" font-size="20">{html.escape(str(drive.get("model", "?")) and f"{drive.get('capacity_gb', 0):.0f} GB")}</text>

<text x="48" y="290" fill="#8888a0" font-family="monospace" font-size="18" letter-spacing="2">ESTIMATED LIFE REMAINING</text>
<text x="48" y="350" fill="#00d4aa" font-family="monospace" font-size="74" font-weight="700">{html.escape(str(months))} months</text>

<rect x="600" y="270" width="552" height="120" fill="#1a1a1f" rx="16"/>
<text x="620" y="305" fill="#8888a0" font-family="monospace" font-size="16" letter-spacing="3">AI ACTIVITY</text>
<text x="620" y="345" fill="#ffffff" font-family="monospace" font-size="28" font-weight="700">{daily:.1f} GB/day</text>
<text x="620" y="375" fill="#8888a0" font-family="monospace" font-size="14">{html.escape(fws[:90])}</text>

<rect x="48" y="430" width="280" height="120" fill="#1a1a1f" rx="16"/>
<text x="68" y="465" fill="#8888a0" font-family="monospace" font-size="14" letter-spacing="3">HEALTH</text>
<text x="68" y="510" fill="#00d4aa" font-family="monospace" font-size="44" font-weight="700">{html.escape(str(health_str))}</text>

<rect x="358" y="430" width="280" height="120" fill="#1a1a1f" rx="16"/>
<text x="378" y="465" fill="#8888a0" font-family="monospace" font-size="14" letter-spacing="3">SHIELD</text>
<text x="378" y="510" fill="#ffffff" font-family="monospace" font-size="20" font-weight="700">{html.escape(str(shield_state))}</text>

<rect x="668" y="430" width="484" height="120" fill="#00d4aa" rx="16"/>
<text x="688" y="465" fill="#0a0a0b" font-family="monospace" font-size="14" letter-spacing="3">GET DRIVE</text>
<text x="688" y="500" fill="#0a0a0b" font-family="monospace" font-size="20" font-weight="700">$14.99 one-time</text>
<text x="688" y="525" fill="#0a0a0b" font-family="monospace" font-size="14">{html.escape(GUMROAD_URL)}</text>

<text x="48" y="600" fill="#666" font-family="monospace" font-size="14">getdrive.io · DRIVE v1.2.0 · Smart local-AI SSD protection</text>
</svg>'''


def build_share_card_png(scan: Dict[str, Any], shield: Optional[Any]) -> bytes:
    """Render the share card as a 1200x630 PNG via Pillow. Designed for Twitter card sizing."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        # Pillow missing in this environment — return the SVG with PNG extension so the
        # user still gets the share asset. UI labels it as SVG when content-type is image/xml.
        return build_share_card_svg(scan, shield).encode()

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (10, 10, 11))
    draw = ImageDraw.Draw(img)
    # Subtle gradient suggestion (single tone — readable everywhere)
    for y in range(H):
        c = 10 + (y * 4 // H)
        draw.line([(0, y), (W, y)], fill=(c, c, c + 6))

    # Try common font paths
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    f_big = f_med = f_small = None
    for p in candidates:
        if os.path.exists(p):
            try:
                f_big = ImageFont.truetype(p, 64)
                f_med = ImageFont.truetype(p, 36)
                f_small = ImageFont.truetype(p, 18)
                break
            except Exception:
                pass
    if not f_big:
        f_big = f_med = f_small = ImageFont.load_default()

    AC = (0, 212, 170)
    TX = (232, 232, 236)
    DIM = (136, 136, 160)

    # Logo box
    draw.rounded_rectangle((48, 48, 200, 108), 10, fill=AC)
    draw.text((124, 60), "DRIVE", fill=(10, 10, 11), font=f_med, anchor="mm")
    draw.text((220, 84), "// AI SSD Guardian", fill=DIM, font=f_small)

    # Header
    draw.text((48, 168), str(scan.get("drive", {}).get("model", "?")), fill=TX, font=f_big)
    cap = scan.get("drive", {}).get("capacity_gb")
    if cap:
        draw.text((48, 218), f"{cap:.0f} GB", fill=DIM, font=f_med)

    # Big stat: life months
    months = scan.get("drive", {}).get("projected_life_months")
    if isinstance(months, (int, float)):
        draw.text((48, 360), f"{months:.0f} months", fill=AC, font=f_big)
    else:
        draw.text((48, 360), "unclear", fill=DIM, font=f_med)
    draw.text((48, 305), "EST. LIFE AT CURRENT AI LOAD", fill=DIM, font=f_small)

    # Right panel: AI activity
    draw.rounded_rectangle((600, 270, 1152, 390), 16, fill=(26, 26, 31))
    daily = scan.get("total_daily_gb", 0)
    draw.text((620, 300), "AI ACTIVITY", fill=DIM, font=f_small)
    draw.text((620, 350), f"{daily:.1f} GB/day", fill=TX, font=f_med)
    fws = ", ".join(sorted({f["name"] for f in scan.get("frameworks", []) if f.get("name")}))[:48]
    if not fws:
        fws = "(no AI frameworks)"
    draw.text((620, 378), fws, fill=DIM, font=f_small)

    # Bottom trio
    draw.rounded_rectangle((48, 430, 328, 550), 16, fill=(26, 26, 31))
    draw.text((68, 460), "HEALTH", fill=DIM, font=f_small)
    h_pct = scan.get("drive", {}).get("health_percent")
    h_str = f"{int(h_pct)}%" if isinstance(h_pct, (int, float)) else "—"
    draw.text((68, 520), h_str, fill=AC, font=f_med)

    draw.rounded_rectangle((358, 430, 638, 550), 16, fill=(26, 26, 31))
    draw.text((378, 460), "SHIELD", fill=DIM, font=f_small)
    shield_state = (shield.state if shield is not None else "not_attempted")
    draw.text((378, 520), str(shield_state), fill=TX, font=f_small)

    # CTA box
    draw.rounded_rectangle((668, 430, 1152, 550), 16, fill=AC)
    draw.text((688, 460), "GET DRIVE", fill=(10, 10, 11), font=f_small)
    draw.text((688, 505), "$14.99 one-time", fill=(10, 10, 11), font=f_med)
    draw.text((688, 536), GUMROAD_URL, fill=(10, 10, 11), font=f_small)

    draw.text((48, 605), "getdrive.io · DRIVE v1.2.0", fill=DIM, font=f_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, dpi=(72, 72))
    return buf.getvalue()
