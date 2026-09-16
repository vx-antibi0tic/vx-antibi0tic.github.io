#!/usr/bin/env python3
"""
build.py — generate the static blog from posts/<slug>/post.md

You write plain markdown (no HTML tags). This script:
  * renders each posts/<slug>/post.md  ->  posts/<slug>/index.html
  * regenerates the post table in index.html (between the POSTS markers)
  * regenerates rss.xml

Usage:
    python build.py               # rebuild everything
    python build.py new <slug>    # scaffold a new post (title prompt optional)

Post format (post.md):

    ---
    title: My Post Title
    date: 08-09-2026
    description: One-line description shown in the index and RSS.
    ---

    Plain text paragraph. Supports **bold**, *italic*, ~~strikethrough~~,
    `inline code`, [links](https://example.com) and bare https:// URLs.
    A line ending in two spaces (or a backslash) forces a line break.

    ## Heading 2
    ### Heading 3

    - list item one
    - list item two
      - nested item (indent with 2+ spaces)

    1. ordered one
    2. ordered two

    - [ ] unchecked task
    - [x] checked task

    > quoted text

    ---

    | Left | Center | Right |
    | :--- | :----: | -----: |
    | a    | b      | c     |

    ```
    plain code block (any language)
    ```

    ```rust
    fn main() { println!("hello"); }   // syntax highlighted
    ```

    ```term
    $ command with prompt
    # comment line
    > output line
    ```

    ![alt text](https://example.com/pic.png)   # full-line image
    (relative paths work too: ![](my-image.png) -> posts/<slug>/my-image.png)

Markdown support: h1-h6, paragraphs, hard line breaks, ul/ol lists
(nestable by indent), task lists, pipe tables with :--- alignment,
blockquote, horizontal rules (---, ***, ___), block/inline images,
fenced code blocks (plain + ```term), inline code/bold/italic/
strikethrough/links, and autolinks for bare http(s) URLs.
Code fences get a language tag (```rust, ```c, ```cpp, ```powershell,
```python, ```asm, ...) which is rendered with highlight.js
(github-dark theme) in the browser.
Language aliases: py, c++, c#, ps/ps1, asm/nasm/x86/x64, sh, js, ts, ...
"""
import datetime
import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(ROOT, "posts")
INDEX_HTML = os.path.join(ROOT, "index.html")
RSS_XML = os.path.join(ROOT, "rss.xml")

# ---- site config -----------------------------------------------------------
SITE_URL = "https://vx-antibi0tic.github.io"
SITE_TITLE = "vx-antibi0tic: infosec blog"
SITE_DESC = "vx-antibi0tic's infosec blog"
SITE_AUTHOR = "vx-antibi0tic"
SITE_GITHUB = "https://github.com/vx-antibi0tic"
FOOTER_YEAR = "2026"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# ---- markdown rendering ----------------------------------------------------

# Fenced-block language aliases -> highlight.js language ids.
# Anything not listed is passed through (hljs knows ~40 common languages).
LANG_ALIASES = {
    "py": "python", "python3": "python",
    "c++": "cpp", "cc": "cpp", "cxx": "cpp",
    "c#": "csharp", "cs": "csharp",
    "asm": "x86asm", "nasm": "x86asm", "masm": "x86asm",
    "x86": "x86asm", "x64": "x86asm", "asmx86": "x86asm",
    "ps": "powershell", "ps1": "powershell",
    "sh": "bash", "shell": "bash", "zsh": "bash",
    "js": "javascript", "ts": "typescript",
    "rb": "ruby", "pl": "perl", "rs": "rust",
    "yml": "yaml", "html": "xml",
    "docker": "dockerfile", "make": "makefile",
}

TERMINAL_LANGS = ("term", "terminal", "console")


def fix_img_url(slug, url):
    """Absolute / protocol-relative URLs pass through; relative paths are
    resolved against the post folder (posts/<slug>/...)."""
    if re.match(r"^(https?:)?//", url) or url.startswith("/"):
        return url
    return "/posts/%s/%s" % (slug, url.lstrip("./"))


def render_image(alt, url, slug):
    url = fix_img_url(slug, url)
    if alt.strip():
        return ('<figure class="post-image">\n'
                '    <img src="%s" alt="%s" loading="lazy">\n'
                '    <figcaption>%s</figcaption>\n'
                '</figure>' % (html.escape(url, quote=True),
                               html.escape(alt), html.escape(alt)))
    return ('<figure class="post-image">\n'
            '    <img src="%s" alt="" loading="lazy">\n'
            '</figure>' % html.escape(url, quote=True))


def render_inline(text, slug=""):
    """Inline markdown -> html. `code` and images first (protected),
    then escape, then links (protected), autolinks, strikethrough,
    bold, italic."""
    protected = []

    def stash(html_str):
        protected.append(html_str)
        return "\x00%d\x00" % (len(protected) - 1)

    # inline code
    text = re.sub(r"`([^`]+)`",
                  lambda m: stash("<code>%s</code>" % html.escape(m.group(1))),
                  text)
    # inline images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                  lambda m: stash('<img src="%s" alt="%s" loading="lazy">'
                                  % (html.escape(fix_img_url(slug, m.group(2)),
                                                 quote=True),
                                     html.escape(m.group(1)))),
                  text)

    text = html.escape(text)
    # links [text](url) — stashed so autolinks don't touch the href
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: stash('<a href="%s">%s</a>'
                                  % (m.group(2), m.group(1))),
                  text)
    # bare http(s) URLs -> links
    def autolink(m):
        url = m.group(0)
        while url and url[-1] in ".,;:!?":
            url = url[:-1]
        if url.count("(") < url.count(")"):
            url = url.rstrip(")")
        trail = m.group(0)[len(url):]
        return stash('<a href="%s">%s</a>' % (url, url)) + trail
    text = re.sub(r"https?://[^\s<>]+", autolink, text)
    # strikethrough, bold, italic
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"\x00(\d+)\x00",
                  lambda m: protected[int(m.group(1))], text)
    return text


def render_term(block_lines):
    """A ```term fenced block -> terminal-styled pre."""
    parts = []
    for ln in block_lines:
        s = ln.strip()
        if s.startswith("$"):
            parts.append('<span class="m-term-prompt">$</span> %s'
                         % html.escape(s[1:].strip()))
        elif s.startswith(">"):
            parts.append('<span class="m-term-prompt">&rarr;</span> %s'
                         % html.escape(s[1:].strip()))
        elif s.startswith("#"):
            parts.append('<span class="m-term-comment">%s</span>'
                         % html.escape(s))
        else:
            parts.append(html.escape(ln))
    return '<pre class="m-term"><code>%s</code></pre>' % "\n".join(parts)


def slugify(text):
    """GitHub-style anchor slug from heading text (lowercase, - for spaces,
    strip anything that isn't a letter/digit/hyphen)."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    return s or "section"


def make_toc(heading_map):
    """heading_map: list of (level, text, anchor) in document order.
    Returns (toc_html, items). items is the same list with de-duplicated
    anchors, or an empty list when there is nothing worth a TOC."""
    if len(heading_map) < 2:
        return "", None  # not enough structure to be useful
    # de-duplicate anchors
    seen = {}
    items = []
    for level, text, anchor in heading_map:
        if anchor in seen:
            seen[anchor] += 1
            anchor = "%s-%d" % (anchor, seen[anchor])
        else:
            seen[anchor] = 0
        items.append((level, text, anchor))

    # TOC html (nested list: h2 top-level, h3 indented)
    lines = []
    for level, text, anchor in items:
        cls = "toc-h2" if level == 2 else "toc-h3"
        lines.append('                    <a class="toc-link %s" href="#%s">%s</a>'
                     % (cls, anchor, html.escape(text)))
    toc_html = ('<aside class="post-toc" id="post-toc">\n'
                '                <div class="toc-title">Contents</div>\n'
                '                <nav class="toc-nav">\n%s\n'
                '                </nav>\n'
                '            </aside>' % "\n".join(lines))
    return toc_html, items


def add_heading_anchors(body_html, items):
    """Insert id="anchor" into the h2/h3 tags of body_html, in order."""
    out = []
    idx = 0
    for ln in body_html.split("\n"):
        m = re.match(r'^(\s*)<h([23])>(.*)</h\2>\s*$', ln)
        if m and idx < len(items):
            _, _, anchor = items[idx]
            lvl = int(m.group(2))
            out.append('%s<h%d id="%s">%s</h%d>'
                       % (m.group(1), lvl, anchor, m.group(3), lvl))
            idx += 1
        else:
            out.append(ln)
    return "\n".join(out)


LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$")


def split_table_row(line):
    """Split a pipe-table row into stripped cells (outer pipes optional)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_table_separator(line):
    """True for a GFM alignment row like | :--- | ---: | :---: | --- |."""
    s = line.strip()
    if "|" not in s or not re.match(r"^[\s|:-]+$", s):
        return False
    cells = split_table_row(s)
    return bool(cells) and all(re.match(r"^:?-+:?$", c) for c in cells)


def render_table(header_cells, sep_cells, body_rows, slug):
    aligns = []
    for c in sep_cells:
        left, right = c.startswith(":"), c.endswith(":")
        aligns.append("center" if (left and right)
                      else "right" if right
                      else "left")

    def cell(text, tag, idx):
        cls = ""
        if idx < len(aligns) and aligns[idx] != "left":
            cls = ' class="ta-%s"' % aligns[idx]
        return "<%s%s>%s</%s>" % (tag, cls, render_inline(text, slug), tag)

    parts = ['<div class="table-wrap">', "<table>", "<thead>", "<tr>"]
    for idx, c in enumerate(header_cells):
        parts.append(cell(c, "th", idx))
    parts += ["</tr>", "</thead>", "<tbody>"]
    for row in body_rows:
        parts.append("<tr>")
        for idx in range(len(header_cells)):
            parts.append(cell(row[idx] if idx < len(row) else "", "td", idx))
        parts.append("</tr>")
    parts += ["</tbody>", "</table>", "</div>"]
    return "\n".join(parts)


def render_list_block(lines, slug):
    """Render a (possibly nested) list from raw lines. The first line must
    be a list item; deeper indentation (spaces) nests. Returns html."""

    def parse(ls, indent):
        m0 = LIST_ITEM_RE.match(ls[0])
        is_ol = m0.group(2)[0].isdigit()
        start = int(m0.group(2)[:-1]) if is_ol else 1
        items = []  # each: [text, child_lines]
        idx = 0
        while idx < len(ls):
            ln = ls[idx]
            m = LIST_ITEM_RE.match(ln)
            ind = len(ln) - len(ln.lstrip())
            if m and ind == indent:
                items.append([m.group(3), []])
                idx += 1
                # nested lines and plain continuation lines for this item
                while idx < len(ls):
                    ln2 = ls[idx]
                    if not ln2.strip():
                        break
                    ind2 = len(ln2) - len(ln2.lstrip())
                    if ind2 > indent:
                        if LIST_ITEM_RE.match(ln2):
                            items[-1][1].append(ln2)
                        else:
                            items[-1][0] += " " + ln2.strip()
                        idx += 1
                    else:
                        break
            elif ln.strip() and items and ind > indent:
                # re-attach after a blank line: nested item or continuation
                if LIST_ITEM_RE.match(ln):
                    items[-1][1].append(ln)
                else:
                    items[-1][0] += " " + ln.strip()
                idx += 1
            else:
                idx += 1  # blank line (or stray line): skip
        tag = "ol" if is_ol else "ul"
        start_attr = ' start="%d"' % start if (is_ol and start != 1) else ""
        lis = []
        for text, children in items:
            mtask = re.match(r"^\[([ xX])\]\s+(.*)$", text)
            if mtask:
                checked = mtask.group(1).lower() == "x"
                li = '<li class="task%s">' % (" done" if checked else "")
                li += ('<input type="checkbox" disabled'
                       + (" checked" if checked else "") + "> ")
                text = mtask.group(2)
            else:
                li = "<li>"
            li += render_inline(text, slug)
            if children:
                cind = len(children[0]) - len(children[0].lstrip())
                li += parse(children, cind)
            li += "</li>"
            lis.append(li)
        return "<%s%s>%s</%s>" % (tag, start_attr, "".join(lis), tag)

    return parse(lines, len(lines[0]) - len(lines[0].lstrip()))


def render_markdown(md, slug=""):
    """Block-level markdown -> (html, headings).
    headings is a list of (level, text, anchor) for h2/h3, in document order."""
    lines = md.split("\n")
    out = []
    para = []  # list of (text, hard_break)
    headings = []
    i = 0

    def flush_para():
        if para:
            parts = []
            for text, br in para:
                parts.append(render_inline(text, slug))
                if br:
                    parts.append("<br>")
            text = " ".join(parts)
            text = text.replace(" <br>", "<br>").replace("<br> ", "<br>")
            out.append("<p>%s</p>" % text)
            para.clear()

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # fenced code block (lang may contain + # . e.g. c++, c#, c#)
        m = re.match(r"^```([\w+#.+-]*)\s*$", stripped)
        if m:
            flush_para()
            lang = m.group(1).strip().lower()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            if lang in TERMINAL_LANGS:
                out.append(render_term(block))
            else:
                hl = LANG_ALIASES.get(lang, lang)
                code = html.escape("\n".join(block))
                if hl:
                    out.append('<pre><code class="language-%s">%s</code></pre>'
                               % (hl, code))
                else:
                    out.append("<pre><code>%s</code></pre>" % code)
            continue

        # pipe table: a line containing | followed by a separator row
        if ("|" in stripped and i + 1 < len(lines)
                and is_table_separator(lines[i + 1])):
            flush_para()
            header_cells = split_table_row(stripped)
            sep_cells = split_table_row(lines[i + 1])
            i += 2
            body_rows = []
            while i < len(lines):
                s2 = lines[i].strip()
                if not s2 or "|" not in s2:
                    break
                body_rows.append(split_table_row(s2))
                i += 1
            out.append(render_table(header_cells, sep_cells, body_rows, slug))
            continue

        # block-level image: a line that is only ![alt](url)
        m = re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)$", stripped)
        if m:
            flush_para()
            out.append(render_image(m.group(1), m.group(2), slug))
            i += 1
            continue

        if not stripped:
            flush_para()
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            text = m.group(2)
            inline_html = render_inline(text, slug)
            out.append("<h%d>%s</h%d>" % (level, inline_html, level))
            if level in (2, 3):
                headings.append((level, text, slugify(text)))
            i += 1
            continue

        # horizontal rule: ---, *** or ___ on a line by itself
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        # list: ul/ol, nestable by indent, task items
        m = LIST_ITEM_RE.match(raw)
        if m:
            flush_para()
            indent0 = len(m.group(1))
            first_ol = m.group(2)[0].isdigit()

            def same_list_item(m2, ind2):
                # continues this list: a nested/continuation line, or a
                # same-type item at the top indent (type change ends it)
                if ind2 > indent0:
                    return True
                if m2 and len(m2.group(1)) == indent0:
                    return m2.group(2)[0].isdigit() == first_ol
                return False

            block = []
            while i < len(lines):
                ln = lines[i]
                if not ln.strip():
                    # blank line: the list continues only if the next
                    # non-blank line is still a list item / nested line
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j >= len(lines):
                        break
                    ln2 = lines[j]
                    m2 = LIST_ITEM_RE.match(ln2)
                    ind2 = len(ln2) - len(ln2.lstrip())
                    if same_list_item(m2, ind2):
                        i = j
                        continue
                    break
                m2 = LIST_ITEM_RE.match(ln)
                ind2 = len(ln) - len(ln.lstrip())
                if same_list_item(m2, ind2):
                    block.append(ln)
                    i += 1
                else:
                    break
            out.append(render_list_block(block, slug))
            continue

        if re.match(r"^>\s?", stripped):
            flush_para()
            quotes = []
            while i < len(lines) and re.match(r"^>\s?", lines[i].strip()):
                quotes.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append("<blockquote><p>%s</p></blockquote>"
                       % render_inline(" ".join(quotes), slug))
            continue

        # paragraph line; two trailing spaces or a trailing backslash
        # force a hard line break
        br = (len(raw) - len(raw.rstrip())) >= 2 or raw.rstrip().endswith("\\")
        if br and raw.rstrip().endswith("\\"):
            stripped = stripped[:-1]
        para.append((stripped, br))
        i += 1

    flush_para()
    return "\n".join(out), headings


# ---- frontmatter / dates ---------------------------------------------------


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("missing frontmatter (--- ... ---) at top of file")
    meta = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    for field in ("title", "date", "description"):
        if field not in meta:
            raise ValueError("frontmatter missing '%s'" % field)
    return meta, m.group(2)


def parse_date(s):
    d, mo, y = s.split("-")
    return datetime.date(int(y), int(mo), int(d))


def rfc822(d):
    return "%s, %02d %s %d 00:00:00 +0000" % (
        WEEKDAYS[d.weekday()], d.day, MONTHS[d.month - 1], d.year)


# ---- templates -------------------------------------------------------------

POST_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>__TITLE__ — vx-antibi0tic</title>
    <meta name="description" content="__DESC__">
    <meta name="author" content="vx-antibi0tic">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">

    <!-- Favicon -->
    <link rel="icon" type="image/svg+xml" href="/favicon.svg">

    <!-- Site styles -->
    <link rel="stylesheet" href="/css/styles.css">

    <!-- Code syntax highlighting (highlight.js, github-dark theme) -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
</head>
<body>
    <!-- Fixed header -->
    <header class="m-header">
        <div class="m-header-inner">
            <a href="/" class="m-brand">vx-antibi0tic</a>
            <nav class="m-nav">
                <a href="/about/">about</a>
                <a href="/" class="m-nav-current">posts</a>
                <a href="/rss.xml">rss</a>
                <a href="__GITHUB__" target="_blank" rel="noopener">github</a>
            </nav>
        </div>
    </header>

    <main class="post-page">
        <div class="post-layout">
            <article>
                <h1>__TITLE__</h1>
                <p class="post-meta">__DATE__</p>

                <div class="post-body">
__BODY__
                    <a class="back-link" href="/">&larr; all posts</a>
                </div>
            </article>
__TOC__
        </div>
    </main>

    <footer class="m-footer">
        <span>Disclaimer: This site is for educational and research purposes only. The author of this site is not responsible for any damages or harm you may suffer by accessing this website or using any information contained herein. The author of this site doesn’t hold any responsibility over the misuse of the software, malware, exploits or security findings contained herein and does not condone them whatsoever. Moreover, the author of the site prohibits any malicious misuse of security informations contained and found here or elsewhere. By continuing to access this website you are agreeing to the full disclaimer presented here and you accept full liability and responsibility. Do not attempt to download Malware samples. The author of this website takes no responsibility for any kind of damages occurring from improper Malware handling or the downloading of ANY Malware mentioned on this website or elsewhere.</span><br><br>
        <span>&copy; __YEAR__ vx-antibi0tic &middot; Malware</span>
    </footer>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <!-- languages not in the default build -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/powershell.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/x86asm.min.js"></script>
    <script>
      hljs.highlightAll();
      // TOC scroll-spy: highlight the section currently in view
      (function () {
        var links = Array.prototype.slice.call(document.querySelectorAll('.toc-link'));
        if (!links.length) return;
        var map = {};
        links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
        var targets = links.map(function (a) {
          return document.getElementById(a.getAttribute('href').slice(1));
        }).filter(Boolean);
        if (!targets.length) return;
        function setActive(id) {
          links.forEach(function (a) { a.classList.remove('active'); });
          if (map[id]) map[id].classList.add('active');
        }
        var OFFSET = 120; // px below viewport top a heading counts as "current"
        var ticking = false;
        function onScroll() {
          if (ticking) return;
          ticking = true;
          requestAnimationFrame(function () {
            ticking = false;
            var current = targets[0];
            for (var i = 0; i < targets.length; i++) {
              if (targets[i].getBoundingClientRect().top - OFFSET <= 0) current = targets[i];
              else break;
            }
            // at the very bottom of the page, force the last section active
            if (window.innerHeight + window.scrollY >=
                document.documentElement.scrollHeight - 4) {
              current = targets[targets.length - 1];
            }
            setActive(current.id);
          });
        }
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('resize', onScroll);
        onScroll();
      })();
    </script>
</body>
</html>
"""

NEW_POST_TEMPLATE = """---
title: My New Post
date: __DATE__
description: One-line description shown in the index and RSS.
---

Write your post here in plain text. **Bold**, *italic*, ~~strike~~,
`inline code`, [links](https://example.com) and bare https:// URLs work.

## A heading

A normal paragraph.

- list item one
- list item two
  - nested item

1. ordered one
2. ordered two

- [ ] task

> quoted text

| Left | Right |
| :--- | ---: |
| a    | b     |

---

```
plain code block
```

```term
$ command
# comment
> output
```
"""


# ---- generation ------------------------------------------------------------


def load_posts():
    posts = []
    for slug in sorted(os.listdir(POSTS_DIR)):
        md_path = os.path.join(POSTS_DIR, slug, "post.md")
        if not os.path.isfile(md_path):
            continue
        with open(md_path, encoding="utf-8") as f:
            text = f.read()
        meta, body_md = parse_frontmatter(text)
        meta["slug"] = slug
        meta["date_obj"] = parse_date(meta["date"])
        body_html, headings = render_markdown(body_md, slug)
        meta["body_html"] = body_html
        toc_html, toc_items = make_toc(headings)
        if toc_items:
            meta["body_html"] = add_heading_anchors(body_html, toc_items)
        meta["toc_html"] = toc_html
        posts.append(meta)
    posts.sort(key=lambda p: p["date_obj"], reverse=True)
    return posts


def indent_body(body_html, indent="                "):
    """Indent structural lines, but never the continuation lines of a
    <pre> block (pre preserves whitespace, so those must stay flush-left)."""
    out = []
    in_pre = False
    for ln in body_html.split("\n"):
        if in_pre:
            out.append(ln)
            if "</pre>" in ln:
                in_pre = False
        else:
            out.append(indent + ln if ln.strip() else "")
            if "<pre" in ln and "</pre>" not in ln:
                in_pre = True
    return "\n".join(out)


def build_post_html(meta):
    body = indent_body(meta["body_html"])
    toc = meta.get("toc_html", "")
    return (POST_TEMPLATE
            .replace("__TITLE__", html.escape(meta["title"]))
            .replace("__DESC__", html.escape(meta["description"]))
            .replace("__DATE__", meta["date"])
            .replace("__GITHUB__", SITE_GITHUB)
            .replace("__YEAR__", FOOTER_YEAR)
            .replace("__TOC__", toc)
            .replace("__BODY__", body))


def build_index(posts):
    rows = []
    for p in posts:
        rows.append(
            '                <tr>\n'
            '                    <td class="col-date">%s</td>\n'
            '                    <td class="col-title"><a href="/posts/%s/" class="blog-title">%s</a></td>\n'
            '                    <td class="col-desc">%s</td>\n'
            '                </tr>'
            % (p["date"], p["slug"],
               html.escape(p["title"]), html.escape(p["description"])))
    block = "\n".join(rows)
    with open(INDEX_HTML, encoding="utf-8") as f:
        html_text = f.read()
    start_marker = "<!-- POSTS:START"
    end_marker = "<!-- POSTS:END -->"
    start = html_text.index(start_marker)
    end = html_text.index(end_marker)
    # keep the whole start comment line, replace everything up to the end marker
    line_end = html_text.index("\n", start)
    html_text = (html_text[:line_end + 1]
                 + block + "\n"
                 + html_text[end:])
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html_text)


def build_rss(posts):
    items = []
    for p in posts:
        url = "%s/posts/%s/" % (SITE_URL, p["slug"])
        items.append(
            "        <item>\n"
            "            <title>%s</title>\n"
            "            <link>%s</link>\n"
            "            <guid>%s</guid>\n"
            "            <pubDate>%s</pubDate>\n"
            "            <description>%s</description>\n"
            "        </item>"
            % (html.escape(p["title"]), url, url,
               rfc822(p["date_obj"]), html.escape(p["description"])))
    latest = rfc822(posts[0]["date_obj"]) if posts else ""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>%s</title>
        <link>%s/</link>
        <atom:link href="%s/rss.xml" rel="self" type="application/rss+xml"/>
        <description>%s</description>
        <language>en-us</language>
        <lastBuildDate>%s</lastBuildDate>

%s
    </channel>
</rss>
""" % (SITE_TITLE, SITE_URL, SITE_URL, SITE_DESC, latest, "\n".join(items))
    with open(RSS_XML, "w", encoding="utf-8") as f:
        f.write(xml)


def new_post(slug):
    d = os.path.join(POSTS_DIR, slug)
    if os.path.exists(os.path.join(d, "post.md")):
        sys.exit("posts/%s/post.md already exists" % slug)
    os.makedirs(d, exist_ok=True)
    today = datetime.date.today()
    text = NEW_POST_TEMPLATE.replace(
        "__DATE__",
        "%02d-%02d-%04d" % (today.day, today.month, today.year))
    with open(os.path.join(d, "post.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print("created posts/%s/post.md — edit it, then run: python build.py"
          % slug)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "new":
        new_post(sys.argv[2])
        return
    posts = load_posts()
    if not posts:
        sys.exit("no posts found (need posts/<slug>/post.md)")
    for p in posts:
        out = os.path.join(POSTS_DIR, p["slug"], "index.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_post_html(p))
        print("built posts/%s/index.html" % p["slug"])
    build_index(posts)
    print("updated index.html")
    build_rss(posts)
    print("updated rss.xml")
    print("done: %d posts" % len(posts))


if __name__ == "__main__":
    main()
