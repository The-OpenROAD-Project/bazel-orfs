#!/usr/bin/env python3
"""Typeset a Markdown file as a PDF: markdown-it-py to HTML, fpdf2 to PDF.

Images are named relative to the Markdown file's directory, or given with
--image <name>=<path>; SVG is drawn as vectors. The text face is DejaVu,
from matplotlib's own data, so that micro signs and arrows print without
anything installed on the host.

  md_to_pdf.py --out README.pdf [--image floorplan.svg=<path>]... <in.md>
"""

import argparse
import datetime
import os
import re

import html as html_lib

import fpdf.html
import matplotlib
from fpdf import FPDF, FontFace, TextStyle
from markdown_it import MarkdownIt

# The page's typography. fpdf2's defaults set lines at 1.0 of the font
# size with next to no space around blocks; these are a printed
# document's.
BODY_PT = 10
TABLE_PT = 8.5
LEADING = 1.45
STYLES = {
    "h1": TextStyle(
        font_family="DejaVu",
        font_style="B",
        font_size_pt=20,
        color="#17202b",
        t_margin=0,
        b_margin=2,
    ),
    "h2": TextStyle(
        font_family="DejaVu",
        font_style="B",
        font_size_pt=14,
        color="#1f5fa8",
        t_margin=7,
        b_margin=1,
    ),
    "h3": TextStyle(
        font_family="DejaVu",
        font_style="B",
        font_size_pt=11.5,
        color="#17202b",
        t_margin=5,
        b_margin=0.5,
    ),
    "p": TextStyle(t_margin=0, b_margin=2),
    "pre": TextStyle(font_family="DejaVuMono", font_size_pt=8, t_margin=1, b_margin=3),
    "ul": TextStyle(t_margin=0, b_margin=2),
    "ol": TextStyle(t_margin=0, b_margin=2),
    "li": TextStyle(l_margin=5, t_margin=1.5),
    "code": FontFace(family="DejaVuMono", size_pt=8.5),
}
# a table row's height in lines of its font
fpdf.html.HTML2FPDF.TABLE_LINE_HEIGHT = 1.5


def fonts():
    d = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    return {
        ("DejaVu", ""): os.path.join(d, "DejaVuSans.ttf"),
        ("DejaVu", "B"): os.path.join(d, "DejaVuSans-Bold.ttf"),
        ("DejaVu", "I"): os.path.join(d, "DejaVuSans-Oblique.ttf"),
        ("DejaVu", "BI"): os.path.join(d, "DejaVuSans-BoldOblique.ttf"),
        ("DejaVuMono", ""): os.path.join(d, "DejaVuSansMono.ttf"),
        ("DejaVuMono", "B"): os.path.join(d, "DejaVuSansMono-Bold.ttf"),
        ("DejaVuMono", "I"): os.path.join(d, "DejaVuSansMono-Oblique.ttf"),
        ("DejaVuMono", "BI"): os.path.join(d, "DejaVuSansMono-BoldOblique.ttf"),
    }


class Doc(FPDF):
    def __init__(self, title):
        super().__init__(format="A4")
        self.doc_title = title
        self.set_margins(22, 20, 22)
        self.set_auto_page_break(True, margin=20)
        for (family, style), path in fonts().items():
            self.add_font(family, style, path)

    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(90, 102, 117)
        self.cell(
            0, 6, "%s   ·   page %d" % (self.doc_title, self.page_no()), align="C"
        )


PAD_MM = 1.4


def svg_aspect(path):
    """An SVG's height over its width, from its width and height attributes."""
    with open(path) as f:
        head = f.read(2000)
    w = re.search(r'<svg[^>]*\swidth="([\d.]+)', head)
    h = re.search(r'<svg[^>]*\sheight="([\d.]+)', head)
    if not (w and h):
        raise SystemExit("md_to_pdf: %s has no width and height" % path)
    return float(h.group(1)) / float(w.group(1))


def column_widths(pdf, table):
    """A table's columns sized from the printed width of their text at the
    table's font, the header in bold: every column as wide as its widest
    cell, so nothing wraps when the table fits the page. Spare width is
    shared out in proportion; when the natural widths overflow, only the
    widest columns give way and wrap. fpdf2 would otherwise give every column the same width.
    """
    rows = re.findall(r"<tr>(.*?)</tr>", table, flags=re.S)
    cells = [re.findall(r"<(t[dh])[^>]*>(.*?)</t[dh]>", r, flags=re.S) for r in rows]
    n = len(cells[0]) if cells else 0
    if n == 0 or any(len(c) != n for c in cells):
        return table
    size = pdf.font_size_pt
    natural = [0.0] * n
    for row in cells:
        for i, (tag, text) in enumerate(row):
            text = html_lib.unescape(re.sub(r"<[^>]+>", "", text)).strip()
            pdf.set_font("DejaVu", "B" if tag == "th" else "", size)
            natural[i] = max(natural[i], pdf.get_string_width(text) + 2 * PAD_MM + 1.0)
    pdf.set_font("DejaVu", "", size)
    room = pdf.epw
    if sum(natural) <= room:
        widths = [w * room / sum(natural) for w in natural]
    else:
        # cap the widest columns at the one width that makes the table
        # fit: only they wrap, every narrower column keeps its line
        lo, hi = 0.0, max(natural)
        for _ in range(60):
            cap = (lo + hi) / 2
            if sum(min(w, cap) for w in natural) > room:
                hi = cap
            else:
                lo = cap
        widths = [min(w, lo) for w in natural]
    total = sum(widths)
    percent = iter(["%.1f%%" % (100.0 * w / total) for w in widths])
    first = rows[0]
    first_new = re.sub(
        r"<(t[dh])",
        lambda m: '<%s width="%s"' % (m.group(1), next(percent)),
        first,
        count=n,
    )
    return table.replace(first, first_new, 1)


def to_html(markdown, images, base):
    md = MarkdownIt("commonmark").enable("table")
    html = md.render(markdown)
    # fpdf2 sets a table cell's text in one style: inline markup in a cell
    # (code, emphasis) goes, its text stays
    html = re.sub(
        r"(<t[dh](?:\s[^>]*)?>)(.*?)(</t[dh]>)",
        lambda m: m.group(1) + re.sub(r"<[^>]+>", "", m.group(2)) + m.group(3),
        html,
        flags=re.S,
    )

    # a paragraph wholly in italics is a note: set in grey, upright, since
    # fpdf2 carries an emphasis that closes a paragraph into the next table
    html = re.sub(
        r"<p><em>(.*?)</em></p>",
        r'<p><font color="#5a6675">\1</font></p>',
        html,
        flags=re.S,
    )

    # leading for running text; a list item takes its list's
    html = re.sub(r"<(p|ul|ol)>", r'<\1 style="line-height: %s">' % LEADING, html)
    # tables: padded cells, text left-aligned and numbers right-aligned as
    # markdown-it marks them (fpdf2 reads align=, not a style, and would
    # justify a cell's text)
    html = html.replace("<table>", '<table cellpadding="1.4">')
    html = re.sub(r'<(t[dh]) style="text-align:right">', r'<\1 align="RIGHT">', html)
    html = re.sub(r"<(t[dh])>", r'<\1 align="LEFT">', html)

    # images become markers: main() places each with pdf.image at the
    # text width, which write_html's <img> does not size reliably
    def marker(m):
        src = m.group(1)
        return "\x00IMG %s\x00" % images.get(src, os.path.join(base, src))

    html = re.sub(r'(?:<p[^>]*>\s*)?<img src="([^"]+)"[^>]*>(?:\s*</p>)?', marker, html)
    return html


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", required=True)
    p.add_argument("--image", action="append", default=[], help="<name>=<path>")
    p.add_argument("--title", default="README")
    p.add_argument("markdown")
    a = p.parse_args(argv)
    images = dict(i.split("=", 1) for i in a.image)
    text = open(a.markdown, encoding="utf-8").read()
    html = to_html(text, images, os.path.dirname(os.path.abspath(a.markdown)))
    pdf = Doc(a.title)
    # a fixed creation date: the same inputs make the same bytes
    pdf.set_creation_date(datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc))
    pdf.add_page()
    pdf.set_font("DejaVu", size=BODY_PT)

    # images are placed, tables set a size smaller than the text, the rest
    # is written as it comes. A break comes before a heading, a table or an
    # image that would start too near the foot of the page: a heading is
    # not left alone at the bottom, nor a table's header row without rows.
    def room():
        return pdf.page_break_trigger - pdf.get_y()

    parts = re.split(
        r"(\x00IMG [^\x00]*\x00|<table.*?</table>|<h[1-6][^>]*>.*?</h[1-6]>)",
        html,
        flags=re.S,
    )
    for part in parts:
        if not part.strip():
            continue
        if part.startswith("\x00IMG "):
            path = part[len("\x00IMG ") : -1]
            height = pdf.epw * svg_aspect(path)
            if height + 7 > room():
                pdf.add_page()
            pdf.ln(3)
            pdf.image(path, w=pdf.epw)
            pdf.ln(4)
            continue
        table = part.startswith("<table")
        if part.startswith("<h") and room() < 45:
            pdf.add_page()
        if table and room() < 30:
            pdf.add_page()
        pdf.set_font("DejaVu", size=TABLE_PT if table else BODY_PT)
        if table:
            part = column_widths(pdf, part)
        pdf.write_html(
            part, font_family="DejaVu", tag_styles=STYLES, table_line_separators=True
        )
    pdf.output(a.out)


if __name__ == "__main__":
    main()
