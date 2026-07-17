"""
Server-side HTML sanitization for campaign / transactional email bodies.

Uses an allowlist (bleach) tuned for HTML email: keeps common structural and
styling tags, links and images, but strips scripts, event handlers, dangerous
URL schemes, and active/embedding content (iframe/object/embed/svg/etc.).

Stored campaign HTML is sanitized on write, so the dashboard never persists or
renders active content. Dashboard previews are ADDITIONALLY isolated in a
sandboxed iframe (defense in depth) — see the frontend.
"""
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

# Remove dangerous container tags AND their content (bleach otherwise keeps the
# inner text of stripped script/style blocks as inert-but-ugly text).
_STRIP_BLOCKS = re.compile(
    r"<(script|style|svg|iframe|object|embed|noscript|title|head|template)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_STRIP_VOID = re.compile(
    r"<(script|style|svg|iframe|object|embed|link|meta|base|noscript)\b[^>]*/?>",
    re.IGNORECASE,
)

# Structural + text + table + media tags typical of HTML email.
ALLOWED_TAGS = [
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "code", "col",
    "colgroup", "div", "em", "figure", "figcaption", "font", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "small", "span",
    "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
    "u", "ul",
]

ALLOWED_ATTRIBUTES = {
    "*": ["style", "class", "align", "valign", "width", "height", "dir", "title"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    "font": ["color", "face", "size"],
    "table": ["border", "cellpadding", "cellspacing", "bgcolor", "role"],
    "td": ["colspan", "rowspan", "bgcolor"],
    "th": ["colspan", "rowspan", "bgcolor"],
    "col": ["span"],
    "colgroup": ["span"],
}

# Only safe URL schemes for links and images (no javascript:, data: for scripts).
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel"]

# Safe CSS properties for inline style="" (blocks expression(), url(javascript:), etc.).
_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    "color", "background-color", "background", "font", "font-family", "font-size",
    "font-weight", "font-style", "text-align", "text-decoration", "line-height",
    "letter-spacing", "margin", "margin-top", "margin-bottom", "margin-left",
    "margin-right", "padding", "padding-top", "padding-bottom", "padding-left",
    "padding-right", "border", "border-radius", "border-color", "border-width",
    "border-style", "width", "max-width", "height", "display", "vertical-align",
    "text-transform", "white-space",
])


def sanitize_email_html(html):
    """Return a sanitized copy of `html` safe to store, preview, and send."""
    if not html:
        return html or ""
    # Pre-strip dangerous tags together with their raw-text content.
    html = _STRIP_BLOCKS.sub("", html)
    html = _STRIP_VOID.sub("", html)
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,           # drop disallowed tags entirely (script/iframe/svg...)
        strip_comments=True,
    )
    return cleaned
