"""One portable, local HTML report: embedded previews, no web dependencies."""
from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote


def render(result: dict[str, Any], destination: Path, created: str) -> str:
    images = result['images']
    def label(index: int) -> str:
        return html.escape(os.path.relpath(images[index]['path'], destination.parent))
    def photo(index: int) -> str:
        image = images[index]
        link = html.escape(quote(os.path.relpath(image['path'], destination.parent)))
        return (f'<figure><a href="{link}"><img loading="lazy" '
                f'src="data:image/jpeg;base64,{image["thumbnail"]}" alt="{label(index)}"></a>'
                f'<figcaption>{label(index)}</figcaption></figure>')
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
             '<title>Related photos</title><style>',
             'body{font:16px system-ui,sans-serif;background:#f7f6f2;color:#242a30;max-width:1400px;margin:0 auto;padding:24px}',
             'h1{margin-bottom:8px}h2{margin-top:40px}.note{color:#525c65;max-width:900px;line-height:1.5}',
             '.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}',
             'figure{margin:0;background:white;border:1px solid #d4d7d8;border-radius:8px;overflow:hidden}',
             'img{width:100%;height:280px;object-fit:contain;background:#e9ebeb}figcaption{padding:10px;font-size:14px;overflow-wrap:anywhere}',
             'section{margin:24px 0;padding:20px;background:#fff;border:1px solid #d4d7d8;border-radius:10px}',
             'summary{cursor:pointer;margin-top:16px}a{color:#155b81}.badge{font-size:14px;font-weight:normal;color:#525c65}',
             'li{margin:8px 0}</style></head><body><h1>Related photos</h1>',
             f'<p>{len(images)} photos · {len(result["groups"])} related sets · {len(result["unmatched"])} unmatched</p>',
             '<p class="note">Candidate groups for your review. Groups can connect through a chain of matches; '
             'not every member necessarily matches every other. “Likely” means stronger evidence, not certainty. '
             'Original images are unchanged; click a preview to open its original.</p>',
             '<p><a href="#likely">Likely groups</a> · <a href="#potential">Potential groups</a> · '
             '<a href="#unmatched">Unmatched</a></p>']
    for level in ('likely', 'potential'):
        parts.append(f'<h2 id="{level}">{level.capitalize()} groups</h2>')
        present = False
        for number, group in enumerate(result['groups'], 1):
            if group['level'] != level:
                continue
            present = True
            members = set(group['members'])
            parts.append(f'<section><h3>Set {number} <span class="badge">{len(members)} photos</span></h3>')
            parts.append('<div class="gallery">' + ''.join(photo(i) for i in group['members']) + '</div>')
            parts.append('<details><summary>Likely and potential connections</summary>')
            for link_level in ('likely', 'potential'):
                links = [p for p in result['pairs'] if p['a'] in members and p['b'] in members and p['level'] == link_level]
                if links:
                    parts.append(f'<h4>{link_level.capitalize()} matches</h4><ul>')
                    parts.extend(f'<li>{label(p["a"])} ↔ {label(p["b"])}</li>' for p in links)
                    parts.append('</ul>')
            parts.append('</details></section>')
        if not present:
            parts.append('<p>None found.</p>')
    parts += ['<h2 id="unmatched">Unmatched photos</h2>',
              '<p class="note">No match was found at the current settings. This does not prove a photo has no related image.</p>',
              '<div class="gallery">' + ''.join(photo(i) for i in result['unmatched']) + '</div>'
              if result['unmatched'] else '<p>Every photo has at least one candidate match.</p>',
              '<footer><p class="note">Analysis ' + html.escape(created) +
              ' · Vision + SIFT · Local report with embedded previews.</p></footer></body></html>']
    return '\n'.join(parts)
