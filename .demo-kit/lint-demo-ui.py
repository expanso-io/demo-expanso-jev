#!/usr/bin/env -S uv run -s
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Objective design gate for Expanso demos.

Checks only things that are measurably right or wrong. Taste, layout and copy
are reviewed adversarially by an agent, not here -- a linter that argues about
aesthetics gets switched off, and a switched-off linter protects nothing.

    lint-demo-ui.py <demo-dir> [<demo-dir> ...]     # report
    lint-demo-ui.py --baseline <parent-dir>         # every demo under a parent

Exit 1 if any ERROR fires. WARNs never fail the build.

Rules, and why each one is objective:

  cdn-font     A demo that fetches fonts at runtime renders in fallback faces
               when conference wifi dies. This is a live-demo failure, not a
               style preference. ERROR.
  emoji        Emoji in markup are a generated-copy tell and render
               inconsistently across the machines demos actually run on. ERROR.
  radius       Every corner radius must come from the scale. Ad-hoc values are
               the single loudest "machine wrote this" signal -- one demo here
               carries 46 distinct ones. ERROR above the threshold.
  type-scale   Font sizes must sit on the scale. Same reasoning as radius.  WARN.
  effects      Gradients, shadows and blurs above a budget. Decoration that
               nothing earned. WARN, because a data-viz demo may justify more.
  internal-scroll Internal scroll containers are forbidden, including hidden
               scrollbars. Only document vertical scrolling is allowed. ERROR.
  contrast     Foreground/background token pairs below WCAG AA (4.5:1). ERROR
               when both tokens resolve to literal colors.
  prose        Paragraph or caption inside [data-region] exceeds 12 words. ERROR.
  empty-stage  Stage region has no child elements. WARN.
  placeholder  Visible text contains placeholders (--, n/a, TBD, placeholder). ERROR.
  timestamp    Feed row contains raw ISO timestamp with T and fractional seconds. WARN.
  callout      [data-region] lacks a .callout child element. WARN.
  lane-color   More than two lanes share one stroke token on a board with 3+ destinations. WARN.
  media-licence An image or SVG under a media/ directory that no LICENSES.md
               in that media/ tree names, by path, file name or backticked
               glob. Bought, downloaded and Paper-drawn graphics all need a
               source and licence line before a demo ships. WARN.

Video-readiness rules (--video, promoted to ERROR by --video-strict). A demo
that only ever gets driven on a 27" monitor can be unrecordable without anyone
noticing; these are the properties a screencast needs and a live demo doesn't.

  video-type   Font sizes that vanish at playback scale. A 1920x1080 capture is
               watched at 1280 or on a phone -- anything under 13px effective
               is gone. The most-skipped fix in every recording so far.
  video-theme  The palette must be the one the demo declares. Boards are dark
               or light by concept and host (agriculture is warm paper, the
               MotherDuck board takes its Dive's light) and the Cloud console is
               matched to the board before recording -- so the check is not
               "is it dark" but "does the literal ground agree with
               `color-scheme`". A light ground under `color-scheme: dark`
               renders dark scrollbars and form controls on a light page, and
               that seam is the loudest thing in the capture.
  video-width  Fixed widths past 1920px force horizontal scroll in a 1080p
               capture.
  video-script Demos that get recorded need a RECORDING_SCRIPT.md. Improvising
               produced a 5:55 take against a 2:01 target.
"""

from __future__ import annotations

import argparse
from collections import Counter
import fnmatch
from html.parser import HTMLParser
import os
import re
import sys
from pathlib import Path

SCAN_SUFFIXES = {".css", ".html", ".jsx", ".tsx", ".svelte", ".vue"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
             ".runtime", ".demo-state", ".next", "vendor", "test-results"}

# The shared scale. Demos pick their own colours and faces, but corners and type
# come off these rails so nothing looks hand-jittered.
# Same seven rails expressed in both units. Tailwind-shaped demos author radii
# in rem and are not wrong to; forcing them onto px would be the linter
# imposing a house style rather than enforcing a scale.
RADIUS_SCALE = {
    "0", "0px",
    "2px", "0.125rem",
    "4px", "0.25rem",
    "8px", "0.5rem",
    "16px", "1rem",
    "9999px", "50%",
    # CSS-wide keywords introduce no new value. `border-radius: inherit` on a
    # child that must follow its parent's corner is correct CSS and was being
    # reported as an eighth rail.
    "inherit", "initial", "unset", "revert", "revert-layer",
}
# Graphics a demo ships under media/. Each needs a source and licence line in
# the nearest media/LICENSES.md (DESIGN_SYSTEM.md, Icons and illustrations).
MEDIA_SUFFIXES = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
BACKTICKED = re.compile(r"`([^`\n]+)`")
EFFECT_BUDGET = 12         # gradients + shadows + blurs per demo

# Below this, text is unreadable once a 1920x1080 capture is watched at 1280
# or on a phone. 13px is the floor; 11px is gone entirely.
VIDEO_MIN_PX = 13.0
VIDEO_HARD_MIN_PX = 11.0
REM_PX = 16.0
BODY_BG = re.compile(
    r"(?:^|[{;\s])(?:body|:root|html)\s*\{[^}]*?background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,8})",
    re.S | re.M)
# The palette the demo says it is. Compared against the literal ground above;
# either value is fine, disagreement is the defect.
COLOR_SCHEME = re.compile(r"color-scheme\s*:\s*(light|dark)\b")
FIXED_WIDTH = re.compile(r"(?:^|[;{\s])width\s*:\s*(\d{3,5})px")

CDN_FONT = re.compile(r"fonts\.(?:googleapis|gstatic)\.com|fonts\.bunny\.net|use\.typekit\.net")

# Pictographic emoji only. Arrows (U+2190-21FF) and geometric shapes
# (U+2B00-2BFF) are legitimate typography -- a data-flow demo drawing "→"
# between stages is doing design, not padding copy with decoration.
# U+231A-23FF is Miscellaneous Technical: the watch, hourglass, alarm and
# media-control pictographs. It was missing, so a screenshot review caught
# an hourglass this check had passed. If a glyph renders as a colour
# pictograph on any platform, it belongs in one of these ranges.
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F000-\U0001F0FF"
                   "\U00002600-\U000027BF\U0000231A-\U000023FF]")

# Check and cross marks default to text presentation, render as a glyph in the
# page's own typeface, and are the conventional way to show pass/fail in a
# status table. They are punctuation doing a job, not decoration.
EMOJI_ALLOWED = set("✓✔✗✘✕×")

# Banned per the global frontend rule: never Inter, Roboto, Arial, or a bare
# system stack for display/body. Mono stacks are exempt -- ui-monospace is the
# conventional way to ask for the platform's code face and reads as deliberate.
BANNED_PRIMARY = {"inter", "inter tight", "roboto", "arial", "helvetica",
                  "helvetica neue", "system-ui", "-apple-system", "segoe ui"}
# Both the longhand and the `font:` shorthand, which is where a banned face
# most often hides -- `font: 16px/1.4 -apple-system, system-ui, ...`.
FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}\n]+)")
FONT_SHORTHAND = re.compile(r"\bfont\s*:\s*[^;}\n]*?(?:\d[\w.%]*(?:/[\w.%]+)?)\s+([^;}\n]+)")
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
RADIUS = re.compile(r"border-radius\s*:\s*([^;}\n]+)")
FONT_SIZE = re.compile(r"font-size\s*:\s*([^;}\n]+)")
EFFECTS = re.compile(r"linear-gradient|radial-gradient|conic-gradient|box-shadow|backdrop-filter|filter\s*:\s*blur")
TOKEN_DEF = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*[;}]")

# Token-name pairs the shared floor guarantees, checked for AA contrast.
#
# Two vocabularies, both first-class. `--text`/`--text-dim` on `--bg` is the
# skeleton new-demo.py stamps. `--ink`/`--muted`/`--quiet` on `--canvas` is the
# three-tier ramp confluent-ai-security and commercial-building-ops arrived at
# independently; it is richer, not a deviation, and it went unchecked here for
# as long as this list did not name it. Anything absent from this list is
# silently unverified, so a new ground or ink name belongs here on the same
# commit that introduces it.
CONTRAST_PAIRS = [
    ("--text", "--bg"), ("--text", "--surface"),
    ("--text-dim", "--bg"), ("--text-dim", "--surface"),
    ("--ink", "--bg"), ("--dim", "--bg"), ("--secondary", "--bg"),
    ("--ink", "--canvas"), ("--ink", "--surface"),
    ("--muted", "--canvas"), ("--muted", "--surface"),
    ("--quiet", "--canvas"), ("--quiet", "--surface"),
    ("--kept", "--bg"), ("--kept", "--surface"),
    ("--kept", "--canvas"),
]


def scan_files(root: Path, suffixes: set[str] = SCAN_SUFFIXES) -> list[Path]:
    """Files to lint: exactly what the demo ships.

    Prefer `git ls-files`, so generated output -- recordings, snapshots,
    evidence bundles, build artifacts -- is skipped for free and stays skipped
    as each demo's .gitignore evolves. Linting generated HTML produces findings
    nobody can act on, and a linter with unactionable findings gets ignored.
    Demos that are not git repositories fall back to a filesystem walk.
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
    )
    if tracked.returncode == 0 and tracked.stdout:
        out = []
        for raw in tracked.stdout.split(b"\0"):
            if not raw:
                continue
            p = root / Path(os.fsdecode(raw))
            if p.suffix.lower() not in suffixes or not p.is_file():
                continue
            # Vendored third-party CSS (reveal.js, a chart lib) is tracked on
            # purpose so the demo works offline; its fonts and radii are not
            # ours to fix. Same skip list as the filesystem walk below.
            if any(part in SKIP_DIRS for part in Path(os.fsdecode(raw)).parts):
                continue
            out.append(p)
        return out

    out = []
    for p in root.rglob("*"):
        if p.suffix.lower() not in suffixes or not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def lint_media_licences(demo: Path, files: list[Path]) -> list[str]:
    """Media graphics that no media/LICENSES.md accounts for."""
    found: list[str] = []
    # One line per unlicensed media/ tree, not one per frame in it.
    unlicensed: Counter[Path] = Counter()
    for f in files:
        rel = f.relative_to(demo)
        parts = rel.parts[:-1]
        if "media" not in parts:
            continue
        # The innermost media/ directory bounds the search; a LICENSES.md
        # nearer the file, as in media/launch/, wins over the one above it.
        media = demo.joinpath(*parts[:len(parts) - parts[::-1].index("media")])
        licence = None
        for d in [f.parent, *f.parent.parents]:
            if (d / "LICENSES.md").is_file():
                licence = d / "LICENSES.md"
                break
            if d == media:
                break
        if licence is None:
            unlicensed[media.relative_to(demo)] += 1
            continue
        text = licence.read_text(errors="replace")
        names = {str(f.relative_to(licence.parent)), str(rel), f.name}
        patterns = BACKTICKED.findall(text)
        if not any(n in text for n in names) and not any(
                fnmatch.fnmatch(n, pat) for n in names for pat in patterns):
            found.append(f"media-licence {rel}: not named in {licence.relative_to(demo)}; "
                         "add its source URL and licence")
    for media_dir, count in sorted(unlicensed.items()):
        found.append(f"media-licence {media_dir}/: {count} graphic(s) and no LICENSES.md")
    return found


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) not in (6, 8):
        raise ValueError(hex_color)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = channel(r), channel(g), channel(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


def _px(value: str) -> float | None:
    """Literal font-size to px. Returns None for var()/calc()/relative units."""
    v = value.strip().lower().replace("!important", "").strip()
    m = re.fullmatch(r"([\d.]+)(px|rem|em|pt)", v)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2)
    return {"px": n, "rem": n * REM_PX, "em": n * REM_PX, "pt": n * 96 / 72}[unit]


def lint_video(demo: Path, files: list[Path]) -> list[str]:
    """Properties a screencast needs that a live demo does not."""
    found: list[str] = []
    small: dict[str, str] = {}
    theme_clash: list[str] = []
    wide: list[str] = []

    for f in files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(demo))
        text = CSS_COMMENT.sub(" ", text)
        text = HTML_COMMENT.sub(" ", text)

        for m in FONT_SIZE.finditer(text):
            px = _px(m.group(1))
            if px is not None and px < VIDEO_MIN_PX:
                small.setdefault(m.group(1).strip(), rel)

        # Palette-agnostic: light and dark are both correct answers. The defect
        # is a literal ground that contradicts the declared color-scheme in the
        # same file. Compared per file, as with contrast -- a landing page and a
        # dashboard are separate documents with separate palettes.
        schemes = set(COLOR_SCHEME.findall(text))
        if len(schemes) == 1:
            scheme = schemes.pop()
            for m in BODY_BG.finditer(text):
                ground = m.group(1)
                renders = "light" if _luminance(ground) > 0.5 else "dark"
                if renders != scheme:
                    theme_clash.append(
                        f"{rel}: ground {ground} renders {renders} under color-scheme: {scheme}"
                    )
                    break

        for m in FIXED_WIDTH.finditer(text):
            if int(m.group(1)) > 1920:
                wide.append(f"{rel}:{m.group(1)}px")

    if small:
        hard = {v: r for v, r in small.items() if (_px(v) or 99) < VIDEO_HARD_MIN_PX}
        shown = ", ".join(sorted(small)[:8]) + (" ..." if len(small) > 8 else "")
        found.append(f"video-type  {len(small)} font-size(s) below {VIDEO_MIN_PX:.0f}px: {shown}"
                     + (f"  [{len(hard)} below {VIDEO_HARD_MIN_PX:.0f}px]" if hard else ""))

    if theme_clash:
        found.append(f"video-theme {theme_clash[0]}; declare the palette you render")

    if wide:
        found.append(f"video-width fixed width past 1920px: {', '.join(wide[:5])}")

    if not (demo / "RECORDING_SCRIPT.md").is_file():
        found.append("video-script no RECORDING_SCRIPT.md; recorded demos need a beat script")

    return found


OVERFLOW_DECL = re.compile(
    r"(?:^|[;\s])overflow(?:-[xy])?\s*:\s*([^;}]+)", re.I)
CSS_LEAF = re.compile(r"([^{}]+)\{([^{}]*)\}")
ROOT_SELECTOR = re.compile(r"(?:html|body|:root)(?:[.#][\w-]+|\[[^\]]+\])*", re.I)


def scroll_declarations(declarations: str) -> list[str]:
    """Literal scroll-enabling declarations; browser tests cover computed CSS."""
    return [m.group(0).strip(" ;\n") for m in OVERFLOW_DECL.finditer(declarations)
            if re.search(r"\b(?:auto|scroll|overlay)\b", m.group(1), re.I)]


def internal_scroll_styles(text: str, *, markup: bool = False) -> list[str]:
    """Find nested CSS rules and HTML style attributes that enable scrolling."""
    found: list[str] = []
    styles: list[str] = []

    class InlineStyles(HTMLParser):
        in_style = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "style":
                self.in_style = True
            if tag in {"html", "body"}:
                return
            for name, value in attrs:
                if name == "style" and value:
                    found.extend(f"<{tag}>: {decl}" for decl in scroll_declarations(value))

        def handle_endtag(self, tag: str) -> None:
            if tag == "style":
                self.in_style = False

        def handle_data(self, data: str) -> None:
            if self.in_style:
                styles.append(data)

    if markup:
        InlineStyles().feed(text)
    else:
        styles.append(text)
    for stylesheet in styles:
        for match in CSS_LEAF.finditer(stylesheet):
            selectors, declarations = match.groups()
            # html/body are the document, but `body .panel` is a nested container.
            if all(ROOT_SELECTOR.fullmatch(s.strip()) for s in selectors.split(",")):
                continue
            for declaration in scroll_declarations(declarations):
                found.append(f"{selectors.strip()}: {declaration}")
    return found


VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
PLACEHOLDER_RE = re.compile(
    r"(?<![a-zA-Z0-9_])--(?![-a-zA-Z0-9_])|\b(?:n/a|tbd|placeholder)\b", re.I
)
ISO_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+")


class DemoUIMarkupParser(HTMLParser):
    def __init__(self, rel: str):
        super().__init__()
        self.rel = rel
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.in_script = False
        self.in_style = False
        self.tag_depth = 0
        self.region_stack: list[dict] = []
        self.stage_info: dict | None = None
        self.prose_elem: dict | None = None
        self.feed_depth: int | None = None
        self.destinations: int = 0
        self.lanes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        classes = (attr_dict.get("class") or "").split()
        id_val = attr_dict.get("id") or ""
        data_region = attr_dict.get("data-region")

        if tag == "script":
            self.in_script = True
        elif tag == "style":
            self.in_style = True

        # Destination tracking: direct elements or children of destination region
        if "destination" in classes or id_val == "destination" or "data-destination" in attr_dict:
            self.destinations += 1
        elif self.region_stack and self.region_stack[-1]["region"] == "destination" and "callout" not in classes:
            self.destinations += 1

        # Stage tracking
        if data_region == "stage" or (not self.stage_info and (id_val == "stage" or "stage" in classes)):
            if not self.stage_info:
                self.stage_info = {"depth": self.tag_depth + 1, "child_count": 0}
        elif self.stage_info and (self.tag_depth + 1) > self.stage_info["depth"]:
            self.stage_info["child_count"] += 1

        # Callout tracking
        if "callout" in classes:
            for r in self.region_stack:
                r["has_callout"] = True

        # Prose tracking (only inside data-regions)
        if self.region_stack:
            if tag in ("p", "caption", "figcaption") or "caption" in classes:
                self.prose_elem = {
                    "tag": tag,
                    "depth": self.tag_depth + 1,
                    "region": self.region_stack[-1]["region"],
                    "text": [],
                }

        # Feed tracking
        if "feed" in classes or id_val == "feed" or "feed-row" in classes:
            if self.feed_depth is None:
                self.feed_depth = self.tag_depth + 1

        # Lane tracking
        if "lane" in classes or any(c.startswith("lane--") for c in classes):
            token = None
            stroke_attr = attr_dict.get("stroke") or ""
            style_attr = attr_dict.get("style") or ""
            m = re.search(r"var\((--[a-z0-9-]+)\)|(--[a-z0-9-]+)|(#[0-9a-fA-F]{3,8})", stroke_attr)
            if m:
                token = m.group(1) or m.group(2) or m.group(3)
            if not token and style_attr:
                m = re.search(r"stroke\s*:\s*(?:var\((--[a-z0-9-]+)\)|(--[a-z0-9-]+)|(#[0-9a-fA-F]{3,8}))", style_attr)
                if m:
                    token = m.group(1) or m.group(2) or m.group(3)
            if not token:
                for c in classes:
                    if c.startswith("lane--") and c not in ("lane--control", "lane--originals", "lane--cut"):
                        token = "--" + c.removeprefix("lane--")
                        break
                    elif c in ("ok", "warn", "err", "accent", "kept"):
                        token = "--" + c
                        break
            if not token:
                token = "default"
            self.lanes.append(token)

        if tag not in VOID_ELEMENTS:
            self.tag_depth += 1
            if data_region:
                self.region_stack.append({"region": data_region, "has_callout": False, "depth": self.tag_depth})

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False
        elif tag == "style":
            self.in_style = False

        if self.prose_elem and self.tag_depth == self.prose_elem["depth"]:
            full_text = " ".join(self.prose_elem["text"]).strip()
            words = full_text.split()
            if len(words) > 12:
                self.errors.append(
                    f"prose      {self.rel}: <{self.prose_elem['tag']}> inside [data-region='{self.prose_elem['region']}'] "
                    f"exceeds 12 words ({len(words)} words)"
                )
            self.prose_elem = None

        if self.region_stack and self.tag_depth == self.region_stack[-1]["depth"]:
            region = self.region_stack.pop()
            if not region["has_callout"]:
                self.warns.append(
                    f"callout    {self.rel}: [data-region='{region['region']}'] lacks a .callout child"
                )

        if self.stage_info and self.tag_depth == self.stage_info["depth"]:
            if self.stage_info["child_count"] == 0:
                self.warns.append(f"empty-stage {self.rel}: stage region has no child elements")
            self.stage_info = None

        if self.feed_depth is not None and self.tag_depth == self.feed_depth:
            self.feed_depth = None

        if tag not in VOID_ELEMENTS and self.tag_depth > 0:
            self.tag_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_script or self.in_style:
            return
        if self.prose_elem:
            self.prose_elem["text"].append(data)

        m = PLACEHOLDER_RE.search(data)
        if m:
            self.errors.append(f"placeholder {self.rel}: visible text contains placeholder '{m.group(0).strip()}'")

        if self.feed_depth is not None:
            m = ISO_TIMESTAMP_RE.search(data)
            if m:
                self.warns.append(f"timestamp  {self.rel}: feed row contains raw ISO timestamp '{m.group(0)}'")

    def finish(self) -> None:
        if self.destinations >= 3 and len(self.lanes) > 2:
            counts = Counter(self.lanes)
            for token, count in counts.items():
                if count > 2:
                    self.warns.append(
                        f"lane-color {self.rel}: stroke token '{token}' shared by {count} lanes on a board with {self.destinations} destinations (max 2)"
                    )


def lint_markup(text: str, rel: str) -> tuple[list[str], list[str]]:
    parser = DemoUIMarkupParser(rel)
    try:
        parser.feed(text)
        parser.finish()
    except Exception:
        pass
    return parser.errors, parser.warns


def lint(demo: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one demo directory."""
    errors: list[str] = []
    warns: list[str] = []
    files = scan_files(demo)
    if not files:
        return errors, warns

    radii: dict[str, int] = {}
    sizes: set[str] = set()
    effects = 0


    for f in files:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        rel = f.relative_to(demo)

        # Comments describe code; they are not code. A stylesheet explaining why
        # it no longer uses a CDN must not be reported as using one.
        text = CSS_COMMENT.sub(" ", text)
        text = HTML_COMMENT.sub(" ", text)

        for declaration in internal_scroll_styles(text, markup=f.suffix.lower() != ".css"):
            errors.append(f"internal-scroll {rel}: {declaration}; use bounded content or pagination")

        for m in CDN_FONT.finditer(text):
            errors.append(f"cdn-font   {rel}: loads fonts from {m.group(0)} at runtime")

        # Only markup files; a CSS `content:` rule is a different question.
        if f.suffix.lower() in {".html", ".jsx", ".tsx", ".svelte", ".vue"}:
            found = {m.group(0) for m in EMOJI.finditer(text)} - EMOJI_ALLOWED
            if found:
                errors.append(f"emoji      {rel}: {' '.join(sorted(found))}")
            m_errs, m_warns = lint_markup(text, str(rel))
            errors.extend(m_errs)
            warns.extend(m_warns)

        for m in RADIUS.finditer(text):
            # `border-radius: 4px !important` and the `/` in the elliptical
            # form are syntax, not values.
            decl = m.group(1).replace("!important", " ").replace("/", " ")
            for token in decl.split():
                token = token.strip()
                if token.startswith("var(") or token.startswith("calc(") or not token:
                    continue
                radii[token] = radii.get(token, 0) + 1

        for m in FONT_SIZE.finditer(text):
            v = m.group(1).strip()
            if not v.startswith("var(") and not v.startswith("clamp("):
                sizes.add(v)

        seen_banned: set[str] = set()
        for pattern in (FONT_FAMILY, FONT_SHORTHAND):
            for m in pattern.finditer(text):
                stack = m.group(1)
                if "monospace" in stack.lower():
                    continue
                primary = stack.split(",")[0].strip().strip("'\"").lower()
                if primary in BANNED_PRIMARY and primary not in seen_banned:
                    seen_banned.add(primary)
                    errors.append(f"font       {rel}: '{primary}' is a banned primary typeface")

        effects += len(EFFECTS.findall(text))

        # Token pairs are compared per file. A demo's landing page and its
        # dashboard are separate documents with separate palettes; pairing
        # --ink from one against --bg from the other invents a failure that
        # cannot happen on screen.
        file_tokens = {m.group(1): m.group(2) for m in TOKEN_DEF.finditer(text)}
        for fg_name, bg_name in CONTRAST_PAIRS:
            fg, bg = file_tokens.get(fg_name), file_tokens.get(bg_name)
            if not fg or not bg:
                continue
            try:
                ratio = contrast_ratio(fg, bg)
            except ValueError:
                continue
            if ratio < 4.5:
                errors.append(
                    f"contrast   {rel}: {fg_name} {fg} on {bg_name} {bg} "
                    f"is {ratio:.1f}:1 (AA needs 4.5:1)"
                )

    # The rule is that every radius comes off the scale, not that a demo may
    # only use some of it. Using all seven rails is correct; using an eighth
    # value is the hand-jittered look this is here to catch.
    off_scale = sorted(v for v in radii if v not in RADIUS_SCALE)
    if off_scale:
        errors.append(
            f"radius     {len(off_scale)} off-scale value(s): {', '.join(off_scale[:10])}"
            + (" ..." if len(off_scale) > 10 else "")
            + f"  [scale: {', '.join(sorted(RADIUS_SCALE))}]"
        )

    if len(sizes) > 8:
        warns.append(f"type-scale {len(sizes)} literal font-size values; move them onto the scale")

    if effects > EFFECT_BUDGET:
        warns.append(f"effects    {effects} gradient/shadow/blur declarations (budget {EFFECT_BUDGET})")

    warns.extend(lint_media_licences(demo, scan_files(demo, MEDIA_SUFFIXES)))

    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--baseline", action="store_true",
                    help="treat each path as a parent directory of demos")
    ap.add_argument("--quiet", action="store_true", help="one line per demo")
    ap.add_argument("--video", action="store_true",
                    help="also check video-readiness (type size, declared theme, width, script)")
    ap.add_argument("--video-strict", action="store_true",
                    help="--video, with the video rules as errors; use for new demos")
    args = ap.parse_args()

    demos: list[Path] = []
    for p in args.paths:
        if args.baseline:
            demos.extend(sorted(d for d in p.iterdir() if d.is_dir() and not d.name.startswith("_")))
        else:
            demos.append(p)

    total_err = 0
    for demo in demos:
        errors, warns = lint(demo)
        if args.video or args.video_strict:
            vid = lint_video(demo, scan_files(demo))
            (errors if args.video_strict else warns).extend(vid)
        total_err += len(errors)
        if args.quiet:
            state = "FAIL" if errors else ("warn" if warns else "ok")
            print(f"  {state:<5} {demo.name:<32} {len(errors)} errors, {len(warns)} warnings")
            continue
        if not errors and not warns:
            print(f"=== {demo.name}: clean")
            continue
        print(f"=== {demo.name}")
        for e in errors:
            print(f"  ERROR  {e}")
        for w in warns:
            print(f"  warn   {w}")
        print()

    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
