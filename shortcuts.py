"""Pre-built shortcut actions that bypass LLM for deterministic tasks.

Combines:
- Quick click patterns (Onyxdrift) for known UI elements
- Search shortcuts (Onyxdrift) with extended site coverage
- Enhanced form detection (all three agents) for login/registration/contact/logout
- Multi-step sequences for compound tasks
"""
from __future__ import annotations
import re
from bs4 import BeautifulSoup

from models import Candidate
from constraint_parser import extract_search_query
from config import SEARCH_INPUT_IDS


def _sel_attr(attribute: str, value: str) -> dict:
    return {"type": "attributeValueSelector", "attribute": attribute, "value": value, "case_sensitive": False}


def _click(attribute: str, value: str) -> list[dict]:
    return [{"type": "ClickAction", "selector": _sel_attr(attribute, value)}]


def _click_xpath(xpath: str) -> list[dict]:
    return [{"type": "ClickAction", "selector": {"type": "xpathSelector", "value": xpath}}]


# ---------------------------------------------------------------------------
# Quick click: regex → fixed element
# ---------------------------------------------------------------------------

_mail_ports = {8005, 8105}
_cal_ports = {8010, 8110}
_work_ports = {8009, 8109}
_drive_ports = {8012, 8112}
_health_ports = {8013, 8113}
_stats_ports = {8014, 8114}
_list_ports = {8011, 8111}


def try_quick_click(prompt: str, url: str, seed: str | None, step: int) -> list[dict] | None:
    t = prompt.lower()

    from urllib.parse import urlsplit
    port = urlsplit(url).port

    # Clear selection (generic)
    if re.search(r"clear\s+(the\s+)?(current\s+)?selection", t):
        return _click_xpath("(//button[@role='checkbox'])[1]")

    # Like a post (autoconnect)
    if port in (8008, 8108) and re.search(r"like\s+(?:the\s+)?(?:post|first\s+post|latest\s+post)", t):
        return _click_xpath("//button[contains(@id, 'like')]")

    # Profile navigation
    if re.search(r"clicks?\s+on\s+.*profile\s+.*in\s+the\s+navbar", t):
        return _click_xpath("//a[contains(@href, '/profile')]")

    # --- Text/xpath-based shortcuts (seed-resilient) ---

    # Navigation shortcuts using href (stable across seeds)
    if seed:
        _s = f"?seed={seed}"
        # Common nav patterns using href (works on all sites)
        nav_map = {
            r"about\s+page|navigate.*about": f"/about{_s}",
            r"help\s+(page|center)|faq|frequently\s+asked": f"/help{_s}",
            r"contact\s+(page|us|support)": f"/contact{_s}",
            r"search\s+page|navigate.*search": f"/search{_s}",
        }
        for pattern, href_suffix in nav_map.items():
            if re.search(pattern, t):
                return _click_xpath(f"//a[contains(@href, '{href_suffix}')]")

    # Cart / Wishlist (text-based, works across sites)
    if re.search(r"view.*cart|shopping\s+cart|my\s+cart|go.*cart", t):
        return _click_xpath("//a[contains(@href, '/cart')] | //button[contains(translate(., 'CART', 'cart'), 'cart')]")
    if re.search(r"view.*wishlist|my\s+wishlist|saved\s+items|favorites?\s+page", t) and not re.search(r"add.*wishlist", t):
        return _click_xpath("//a[contains(@href, '/wishlist') or contains(@href, '/favorites')] | //button[contains(translate(., 'WISHLIST', 'wishlist'), 'wishlist') or contains(translate(., 'FAVORITES', 'favorites'), 'favorites')]")

    # Compose / Create actions (text-based)
    if port in _mail_ports and re.search(r"compose|write.*(?:email|mail)|new\s+(?:email|mail)", t):
        return _click_xpath("//button[contains(translate(., 'COMPOSE', 'compose'), 'compose')]")

    # Template section (automail)
    if port in _mail_ports and re.search(r"template|open.*template", t) and "edit" not in t and "send" not in t and "cancel" not in t and "save" not in t:
        return _click_xpath("//button[contains(translate(., 'TEMPLATES', 'templates'), 'template')]")

    # Sidebar navigation (automail - text-based)
    if port in _mail_ports:
        mail_nav = {
            r"^(?:go\s+to\s+)?inbox": "Inbox",
            r"starred|go.*starred": "Starred",
            r"drafts|go.*drafts": "Drafts",
            r"sent\s+(?:mail|folder|page)|go.*sent": "Sent",
            r"trash|go.*trash": "Trash",
            r"spam|go.*spam": "Spam",
            r"important|go.*important": "Important",
            r"snoozed|go.*snoozed": "Snoozed",
            r"archive|go.*archive": "Archive",
        }
        for pattern, label in mail_nav.items():
            if re.search(pattern, t):
                return _click_xpath(f"//button[starts-with(normalize-space(.), '{label}')] | //a[starts-with(normalize-space(.), '{label}')]")

    # Create label (automail - xpath)
    if port in _mail_ports and "create" in t and "label" in t:
        if step == 0:
            return _click_xpath("//button[contains(translate(., 'LABEL', 'label'), 'label') and contains(translate(., 'CREATE', 'create'), 'creat')]")
        elif step == 1:
            m2 = re.search(r"(?:equal to |equals? |CONTAINS )['\"]([^'\"]+)['\"]", prompt)
            label_text = m2.group(1) if m2 else "label"
            return [{"type": "TypeAction", "text": label_text,
                     "selector": {"type": "xpathSelector",
                                  "value": "//input[contains(@id, 'label') or contains(@placeholder, 'label') or contains(@placeholder, 'Label')]"}}]
        elif step == 2:
            return _click_xpath("//button[contains(translate(., 'ADD', 'add'), 'add') and contains(translate(., 'LABEL', 'label'), 'label')]")
        return []

    # Theme change (text-based)
    if re.search(r"change.*theme|theme.*(?:dark|light|system)", t):
        return _click_xpath("//button[contains(@id, 'theme') or contains(@aria-label, 'theme') or contains(@aria-label, 'Theme')]")

    # FAQ toggle (autodining, autolodge - click question text)
    if re.search(r"faq.*toggle|show.*faq|details.*faq", t):
        m2 = re.search(r"(?:CONTAINS|contains|question\s+(?:is|equals))\s+['\"]([^'\"]+)['\"]", prompt)
        if m2:
            q = m2.group(1)
            return _click_xpath(f"//button[contains(., '{q}')] | //*[contains(@id, 'faq') and contains(., '{q}')]")
        # NOT pattern
        m2 = re.search(r"NOT\s+['\"]([^'\"]+)['\"]", prompt)
        if m2:
            # Click first FAQ that doesn't match
            return None  # Let LLM handle NOT patterns

    # Calendar navigation (text-based, autocalendar)
    if port in _cal_ports:
        if re.search(r"previous\s+(?:month|week|day)|go\s+back", t):
            return _click_xpath("//button[contains(@id, 'previous') or contains(@id, 'prev')]")
        if re.search(r"next\s+(?:month|week|day)|go\s+forward", t):
            return _click_xpath("//button[contains(@id, 'next')]")
        if re.search(r"today|go.*today|focus.*today", t):
            return _click_xpath("//button[contains(@id, 'today') or contains(translate(., 'TODAY', 'today'), 'today')]")
        if re.search(r"create.*event|new\s+event|add\s+event|schedule", t) and "calendar" not in t:
            return _click_xpath("//button[contains(@id, 'new-event') or contains(@id, 'create') or contains(translate(., 'SCHEDULE', 'schedule'), 'schedule')]")
        for view_name in ("day", "week", "month"):
            if f"switch to {view_name}" in t or f"{view_name} view" in t:
                return _click_xpath(f"//button[contains(@id, 'view') or contains(translate(., '{view_name.upper()}', '{view_name}'), '{view_name}')]")

    # Autowork (text-based)
    if port in _work_ports:
        if re.search(r"hires|hire.*dashboard", t):
            return _click_xpath("//a[contains(@href, '/hires')]")
        if re.search(r"jobs|job.*dashboard", t):
            return _click_xpath("//a[contains(@href, '/jobs')]")
        if re.search(r"skills|skill.*page", t):
            return _click_xpath("//a[contains(@href, '/skills')]")
        if re.search(r"create.*posting|post.*job|new.*job", t):
            return _click_xpath("//button[contains(translate(., 'POST', 'post'), 'post') or contains(translate(., 'CREATE', 'create'), 'creat')]")
        if "consultation" in t:
            return _click_xpath("//button[contains(translate(., 'CONSULT', 'consult'), 'consult')]")

    # Autodrive (text-based)
    if port in _drive_ports:
        if re.search(r"my\s+trips?|trip.*history|view.*trips?", t):
            return _click_xpath("//a[contains(@href, 'trip') or contains(translate(., 'TRIPS', 'trips'), 'trip')]")
        if re.search(r"book\s+(?:a\s+)?ride|request\s+ride|pickup\s+now|ride\s+now", t):
            return _click_xpath("//button[contains(translate(., 'BOOK', 'book'), 'book') or contains(translate(., 'RIDE', 'ride'), 'ride')]")

    # Autohealth (text-based)
    if port in _health_ports:
        if re.search(r"book\s+(?:an?\s+)?appointment|request\s+appointment|schedule.*appointment", t):
            return _click_xpath("//button[contains(translate(., 'APPOINTMENT', 'appointment'), 'appointment') or contains(translate(., 'RESERVE', 'reserve'), 'reserv')]")

    # Autostats (text-based)
    if port in _stats_ports:
        if re.search(r"connect.*wallet|authorize.*wallet", t):
            return _click_xpath("//button[contains(translate(., 'WALLET', 'wallet'), 'wallet')]")

    # Autolist (text-based)
    if port in _list_ports:
        if re.search(r"add\s+(?:a\s+)?task|create.*task|new\s+task", t):
            return _click_xpath("//button[contains(translate(., 'ADD TASK', 'add task'), 'add task')]")

    return None


# ---------------------------------------------------------------------------
# Search shortcut: direct type into known search input
# ---------------------------------------------------------------------------

def try_search_shortcut(prompt: str, website: str | None) -> list[dict] | None:
    if not website:
        return None
    query = extract_search_query(prompt)
    if not query:
        return None
    # Use xpath to find search input - resilient to ID changes across seeds
    search_xpath = ("//input[@type='search' or @type='text']"
                    "[contains(@id, 'search') or contains(@placeholder, 'earch') "
                    "or contains(@placeholder, 'query') or contains(@placeholder, 'filter') "
                    "or contains(@name, 'search') or contains(@name, 'query')]")
    return [{"type": "TypeAction", "text": query,
             "selector": {"type": "xpathSelector", "value": search_xpath}}]


# ---------------------------------------------------------------------------
# Form-based shortcuts
# ---------------------------------------------------------------------------

def is_already_logged_in(soup: BeautifulSoup) -> bool:
    indicators = ["logout", "log out", "sign out", "my profile", "my account", "dashboard"]
    text = soup.get_text(separator=" ").lower()
    return any(ind in text for ind in indicators)


def detect_login_fields(candidates: list[Candidate]) -> list[dict] | None:
    username = password = submit = None

    for c in candidates:
        # Username field
        if username is None and c.tag == "input":
            if c.name in {"username", "user", "email", "login"}:
                username = c
            elif c.input_type in {"email", "text"} and c.placeholder and (
                "user" in c.placeholder.lower() or "email" in c.placeholder.lower()
            ):
                username = c

        # Password field
        if password is None and c.input_type == "password":
            password = c

        # Submit button
        if submit is None and c.tag in {"button", "input"}:
            if c.input_type == "submit":
                submit = c
            elif c.text and any(
                kw in c.text.lower()
                for kw in ("log in", "login", "sign in", "submit", "enter", "continue")
            ):
                submit = c

    if username and password and submit:
        return [
            {"type": "TypeAction", "text": "<username>", "selector": username.selector.model_dump()},
            {"type": "TypeAction", "text": "<password>", "selector": password.selector.model_dump()},
            {"type": "ClickAction", "selector": submit.selector.model_dump()},
        ]
    return None


def detect_logout_target(candidates: list[Candidate]) -> list[dict] | None:
    for c in candidates:
        if c.text and any(kw in c.text.lower() for kw in ("log out", "logout", "sign out")):
            return [{"type": "ClickAction", "selector": c.selector.model_dump()}]
    # Try href-based
    for c in candidates:
        if c.href and any(kw in c.href.lower() for kw in ("logout", "signout", "sign-out")):
            return [{"type": "ClickAction", "selector": c.selector.model_dump()}]
    return None


def get_registration_actions(candidates: list[Candidate]) -> list[dict] | None:
    username = email = password = confirm = submit = None
    password_seen = False

    for c in candidates:
        if username is None and c.tag == "input":
            if c.name in {"username", "user"} or (c.placeholder and "username" in c.placeholder.lower()):
                username = c

        if email is None and c.tag == "input":
            if c.input_type == "email" or c.name == "email" or (
                c.placeholder and "email" in c.placeholder.lower()
            ):
                email = c

        if c.input_type == "password" or (c.name and "password" in c.name.lower()):
            if not password_seen:
                password = c
                password_seen = True
            elif confirm is None:
                confirm = c

        if submit is None and c.tag in {"button", "input"}:
            if c.input_type == "submit":
                submit = c
            elif c.text and any(
                kw in c.text.lower()
                for kw in ("register", "sign up", "signup", "create", "submit")
            ):
                submit = c

    if not password or not submit:
        return None
    if not username and not email:
        return None

    actions: list[dict] = []
    if username:
        actions.append({"type": "TypeAction", "text": "<signup_username>", "selector": username.selector.model_dump()})
    if email:
        actions.append({"type": "TypeAction", "text": "<signup_email>", "selector": email.selector.model_dump()})
    actions.append({"type": "TypeAction", "text": "<signup_password>", "selector": password.selector.model_dump()})
    if confirm:
        actions.append({"type": "TypeAction", "text": "<signup_password>", "selector": confirm.selector.model_dump()})
    actions.append({"type": "ClickAction", "selector": submit.selector.model_dump()})
    return actions


def get_contact_actions(candidates: list[Candidate]) -> list[dict] | None:
    name_c = email_c = message_c = submit_c = None

    for c in candidates:
        if name_c is None and c.tag == "input":
            if c.name in {"name", "full_name", "fullname", "your_name"} or (
                c.placeholder and "name" in c.placeholder.lower()
            ):
                name_c = c

        if email_c is None and c.tag == "input":
            if c.name == "email" or c.input_type == "email" or (
                c.placeholder and "email" in c.placeholder.lower()
            ):
                email_c = c

        if message_c is None:
            if c.tag == "textarea":
                message_c = c
            elif c.name in {"message", "msg", "content", "body", "subject"}:
                message_c = c

        if submit_c is None and c.tag in {"button", "input"}:
            if c.input_type == "submit":
                submit_c = c
            elif c.text and any(kw in c.text.lower() for kw in ("send", "submit", "contact")):
                submit_c = c

    if not submit_c:
        return None
    # At minimum need message OR (name + email)
    if not message_c and (not name_c or not email_c):
        return None

    actions: list[dict] = []
    if name_c:
        actions.append({"type": "TypeAction", "text": "Test User", "selector": name_c.selector.model_dump()})
    if email_c:
        actions.append({"type": "TypeAction", "text": "<signup_email>", "selector": email_c.selector.model_dump()})
    if message_c:
        actions.append({"type": "TypeAction", "text": "Hello, this is a test message for support.", "selector": message_c.selector.model_dump()})
    actions.append({"type": "ClickAction", "selector": submit_c.selector.model_dump()})
    return actions


def try_shortcut(
    task_type: str | None,
    candidates: list[Candidate],
    soup: BeautifulSoup,
    step_index: int,
) -> list[dict] | None:
    """Attempt deterministic shortcut for the given task type."""
    if task_type is None:
        return None

    if task_type == "login":
        if is_already_logged_in(soup):
            return [{"type": "WaitAction", "time_seconds": 1}]
        return detect_login_fields(candidates)

    if task_type == "logout":
        result = detect_logout_target(candidates)
        if result:
            return result
        # May need to login first, then logout
        if not is_already_logged_in(soup):
            login = detect_login_fields(candidates)
            if login:
                return login
        return None

    if task_type == "registration":
        return get_registration_actions(candidates)

    if task_type == "contact":
        return get_contact_actions(candidates)

    return None
