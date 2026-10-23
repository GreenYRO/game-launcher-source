"""The comparison as a report (Phase 81): one HTML page in Romanian, with its numbers as CSV files.

The page is self-contained -- its charts are SVG drawn here, its style and its one small script
inline; it fetches nothing. Every chart has its numbers as a table beside it, and hovering or
focusing a mark shows its value, so nothing is read by colour alone. Light and dark follow the
system. Colours are the dataviz reference palette (rules.REPORT_*), validated for colour-blind
readers before use (Phase 81 notes).

The CSV files are for Excel in Romanian: semicolons between fields, decimal commas, UTF-8 with
the mark Excel needs to see it.

Names in the exports are the friends' data: every one is escaped before it reaches the page.
"""

from __future__ import annotations

import csv
import html
import json
import logging
from datetime import date
from pathlib import Path

from logic import comparison
from shared import rules
from shared import version

log = logging.getLogger(__name__)

SOURCE_WORDS = {"steam": "Steam", "folders": "foldere", "gog": "GOG", "epic": "Epic", "xbox": "Xbox",
                "ubisoft": "Ubisoft", "unknown": "neînregistrat"}
WEEKDAYS_RO = {"Mon": "Lu", "Tue": "Ma", "Wed": "Mi", "Thu": "Jo", "Fri": "Vi", "Sat": "Sâ", "Sun": "Du"}
STATUS_RO = {"playing": "în curs", "finished": "terminate", "dropped": "abandonate"}


def num(value: float, decimals: int = 0) -> str:
    """1234.5 -> "1.234,5": as Romanian writes it."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def hours(minutes: float) -> str:
    return num(minutes / 60, 1)


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def _set_aside_line(people) -> str:
    """What was left out of every measure, and how much of each participant's time (Phase 83)."""
    names = " și ".join(rules.STEAM_NOT_GAMES.values())
    held = [f"{p.label} {hours(p.set_aside_minutes)} ore" for p in people if p.set_aside_minutes]
    return (f"{names} sunt lăsate deoparte peste tot: orele lor sunt ale altor jocuri (un joc care folosește "
            "Steam fără să fie vândut acolo își raportează timpul sub Spacewar; modurile Source rulează pe SDK). "
            + (f"Lăsat deoparte: {', '.join(held)}." if held else "Niciun participant nu are timp pe ele."))


# -- the charts ------------------------------------------------------------------------------

def _ticks(top: float, count: int = 4) -> list[float]:
    """Round tick values from 0 to at least `top`."""
    if top <= 0:
        return [0.0]
    raw = top / count
    magnitude = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 0.1
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    ticks = [0.0]
    while ticks[-1] < top:  # the last tick at or past the largest value: no bar runs off its axis
        ticks.append(ticks[-1] + step)
    return ticks


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "\u2026"


def hbar_chart(rows: list[tuple[str, float, str]], fmt, slot: int = 1, width: int = 480, left: int = 56,
               label_chars: int = 12, top: float | None = None) -> str:
    """Horizontal bars, one series: (label, value, tooltip). Value at each bar's tip. Drawn at the width
    it is shown at, never wider, so its words stay their size."""
    right, bar, gap = 56, 18, 10
    # Small multiples share one scale (`top`): otherwise equal bars in two of them mean different things.
    top = max((v for _l, v, _t in rows), default=0) if top is None else top
    ticks = _ticks(top)
    scale = (width - left - right) / (ticks[-1] or 1)
    height = len(rows) * (bar + gap) + 28
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" style="max-width:{width}px">']
    for t in ticks:
        x = left + t * scale
        parts.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="0" y2="{height - 22}"/>'
                     f'<text class="tick" x="{x:.1f}" y="{height - 6}" text-anchor="middle">{esc(fmt(t))}</text>')
    for i, (label, value, tip) in enumerate(rows):
        y = i * (bar + gap) + 6
        length = max(value * scale, 0)
        parts.append(f'<text class="label" x="{left - 8}" y="{y + bar / 2 + 4}" text-anchor="end">'
                     f'<title>{esc(label)}</title>{esc(_short(label, label_chars))}</text>')
        if length > 0:
            r = min(4, length / 2)
            parts.append(f'<path class="mark s{slot}" tabindex="0" data-tip="{esc(tip)}" d="M{left},{y} '
                         f'h{length - r:.1f} q{r},0 {r},{r} v{bar - 2 * r} q0,{r} -{r},{r} h-{length - r:.1f} z"/>')
        parts.append(f'<text class="value" x="{left + length + 6:.1f}" y="{y + bar / 2 + 4}">{esc(fmt(value))}</text>')
    parts.append(f'<line class="axis" x1="{left}" x2="{left}" y1="0" y2="{height - 22}"/></svg>')
    return "".join(parts)


def stacked_chart(rows: list[tuple[str, dict]], keys: list[str], words: dict) -> str:
    """Horizontal 100% stacked bars with a 2 px surface gap between parts; a legend above."""
    width, left, bar, gap = 1000, 44, 20, 14
    plot = width - left - 10
    height = len(rows) * (bar + gap) + 6
    legend = "".join(f'<span class="key"><i class="sw s{n + 1}"></i>{esc(words.get(k, k))}</span>'
                     for n, k in enumerate(keys))
    parts = [f'<div class="legend">{legend}</div><svg class="chart" viewBox="0 0 {width} {height}" role="img" '
             f'style="max-width:{width}px">']
    for i, (label, counts) in enumerate(rows):
        y = i * (bar + gap) + 4
        total = sum(counts.values())
        parts.append(f'<text class="label" x="{left - 8}" y="{y + bar / 2 + 4}" text-anchor="end">{esc(label)}</text>')
        x = left
        present = [k for k in keys if counts.get(k)]
        for n, key in enumerate(keys):
            value = counts.get(key, 0)
            if not value or not total:
                continue
            w = plot * value / total - (2 if key != present[-1] else 0)
            tip = f"{label} · {words.get(key, key)}: {value} ({num(100 * value / total, 1)}%)"
            parts.append(f'<rect class="mark s{n + 1}" tabindex="0" data-tip="{esc(tip)}" x="{x:.1f}" y="{y}" '
                         f'width="{max(w, 1):.1f}" height="{bar}" rx="{2 if w > 6 else 0}"/>')
            x += plot * value / total
    parts.append("</svg>")
    return "".join(parts)


def columns_chart(values: list[tuple[str, float]], label_every: int = 1, peak: float | None = None) -> str:
    """A small column chart, one series (shares in percent): the hour of the day, the weekday."""
    width, height, base, top_pad = 300, 120, 100, 12
    n = len(values)
    slot = (width - 10) / n
    bar = min(24, slot - 2)
    peak = (max((v for _l, v in values), default=0) if peak is None else peak) or 1  # shared by a set
    parts = [f'<svg class="chart small" viewBox="0 0 {width} {height}" role="img" style="max-width:{width}px">'
             f'<line class="axis" x1="5" x2="{width - 5}" y1="{base}" y2="{base}"/>']
    for i, (label, value) in enumerate(values):
        x = 5 + i * slot + (slot - bar) / 2
        h = (base - top_pad) * value / peak
        if h > 0:
            r = min(4, h / 2, bar / 2)
            parts.append(f'<path class="mark s1" tabindex="0" data-tip="{esc(label)}: {num(value, 1)}%" '
                         f'd="M{x:.1f},{base} v-{h - r:.1f} q0,-{r} {r},-{r} h{bar - 2 * r:.1f} q{r},0 {r},{r} '
                         f'v{h - r:.1f} z"/>')
        if i % label_every == 0:
            parts.append(f'<text class="tick" x="{x + bar / 2:.1f}" y="{base + 14}" text-anchor="middle">{esc(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heatmap(labels: list[str], matrix: dict) -> str:
    """The similarity map: one cell per pair, the blue ramp light to dark, the value written in it."""
    cell, left, top = 52, 40, 24
    size = len(labels)
    width, height = left + size * cell + 4, top + size * cell + 4
    parts = [f'<svg class="chart heat" viewBox="0 0 {width} {height}" role="img" style="max-width:{width * 1.2:.0f}px">']
    for j, label in enumerate(labels):
        parts.append(f'<text class="label" x="{left + j * cell + cell / 2}" y="{top - 8}" text-anchor="middle">{esc(label)}</text>')
    for i, row in enumerate(labels):
        parts.append(f'<text class="label" x="{left - 8}" y="{top + i * cell + cell / 2 + 4}" text-anchor="end">{esc(row)}</text>')
        for j, col in enumerate(labels):
            value = matrix.get((row, col))
            x, y = left + j * cell, top + i * cell
            if value is None:
                parts.append(f'<rect class="empty" x="{x + 1}" y="{y + 1}" width="{cell - 2}" height="{cell - 2}" rx="4"/>')
                continue
            step = min(len(rules.REPORT_RAMP) - 1, int(value * (len(rules.REPORT_RAMP) - 1) + 0.5))
            ink = "light" if step >= 3 else "dark"
            text = "—" if row == col else num(value, 2)
            parts.append(f'<rect class="cell" tabindex="0" style="fill:{rules.REPORT_RAMP[step]}" '
                         f'data-tip="{esc(row)} și {esc(col)}: {num(value, 2)}" x="{x + 1}" y="{y + 1}" '
                         f'width="{cell - 2}" height="{cell - 2}" rx="4"/>'
                         f'<text class="cellv {ink}" x="{x + cell / 2}" y="{y + cell / 2 + 4}" '
                         f'text-anchor="middle">{text}</text>')
    parts.append("</svg>")
    return "".join(parts)


def table(head: list[str], rows: list[list], numeric_from: int = 1, cls: str = "") -> str:
    cells = "".join(f'<th{" class=n" if i >= numeric_from else ""}>{esc(h)}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f'<td{" class=n" if i >= numeric_from else ""}>{esc(v)}</td>'
                                    for i, v in enumerate(row)) + "</tr>" for row in rows)
    return f'<table{f" class={cls}" if cls else ""}><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table>'


def figure(title: str, note: str, chart: str, data_table: str) -> str:
    return (f'<section class="card"><h2>{esc(title)}</h2><p class="note">{esc(note)}</p>{chart}'
            f'<details><summary>Tabelul cu cifrele</summary>{data_table}</details></section>')


# -- the page --------------------------------------------------------------------------------

STYLE = """
.viz-root{color-scheme:light;--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);%(light)s}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
--ring:rgba(255,255,255,.10);%(dark)s}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);%(dark)s}
html,body{margin:0;background:var(--page)}
.viz-root{background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
padding:24px 16px 48px}
.wrap{max-width:1080px;margin:0 auto}
h1{font-size:28px;font-weight:600;margin:0 0 4px}
h2{font-size:18px;font-weight:600;margin:0 0 4px}
h3{font-size:14px;font-weight:600;margin:0 0 4px;color:var(--ink2)}
.meta,.note{color:var(--ink2);margin:0 0 12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:20px;margin:16px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.pair>.card{margin:0}
table.nowrap td{white-space:nowrap}
.multiple{border-top:1px solid var(--grid);padding-top:10px}
svg.chart{width:100%%;height:auto;display:block;overflow:visible}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .axis{stroke:var(--axis);stroke-width:1}
svg .tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
svg .label{fill:var(--ink2);font-size:12px}
svg .value{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}
svg .mark:focus,svg .cell:focus{outline:none;stroke:var(--ink);stroke-width:2}
svg .empty{fill:var(--grid)}
svg .cellv{font-size:12px;font-variant-numeric:tabular-nums}
svg .cellv.dark{fill:#0b0b0b} svg .cellv.light{fill:#fff}
%(slots)s
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin:0 0 8px;color:var(--ink2);font-size:13px}
.key{display:inline-flex;align-items:center;gap:6px}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px}
table{border-collapse:collapse;width:100%%;font-size:13px;margin:8px 0}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--grid)}
th{color:var(--ink2);font-weight:600}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
details{margin-top:8px} summary{cursor:pointer;color:var(--ink2);font-size:13px}
.scroll{overflow-x:auto}
ul.plain{margin:0;padding-left:18px;color:var(--ink2)}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);
border-radius:8px;padding:6px 10px;font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.15);display:none;max-width:320px}
"""

SCRIPT = """
(function(){var tip=document.getElementById('tip');
function show(el,x,y){tip.textContent=el.getAttribute('data-tip');tip.style.display='block';
var w=tip.offsetWidth,h=tip.offsetHeight;var l=Math.min(x+14,window.innerWidth-w-8),t=y-h-12;if(t<8)t=y+18;
tip.style.left=l+'px';tip.style.top=t+'px';}
function hide(){tip.style.display='none';}
document.querySelectorAll('[data-tip]').forEach(function(el){
el.addEventListener('pointermove',function(e){show(el,e.clientX,e.clientY);});
el.addEventListener('pointerleave',hide);
el.addEventListener('focus',function(){var r=el.getBoundingClientRect();show(el,r.left+r.width/2,r.top);});
el.addEventListener('blur',hide);});})();
"""


def _style() -> str:
    light = "".join(f"--s{n}:{c};" for n, c in enumerate(rules.REPORT_SERIES_LIGHT, 1))
    dark = "".join(f"--s{n}:{c};" for n, c in enumerate(rules.REPORT_SERIES_DARK, 1))
    slots = "".join(f".s{n}{{fill:var(--s{n});background:var(--s{n})}}" for n in range(1, 9))
    return STYLE % {"light": light, "dark": dark, "slots": slots}


def _rated(p) -> str:
    """A participant's ratings in the overview: none asked for in an export older than format 3 -- never "0"."""
    if p.ratings is None:
        return f"— (format {p.data.get('version')})"
    if not p.ratings:
        return "niciuna"
    return f"{p.ratings} pe {p.rated_games} jocuri, media {num(p.mean_stars, 1)}"


def page(loaded: comparison.Loaded, today: date | None = None) -> str:
    people = loaded.participants
    today = today or date.today()
    sections = []

    overview_rows = [[p.label, p.data.get("made_on") or "?", p.installed, p.games, hours(p.launcher_minutes),
                      p.sessions, num(p.session_minutes / p.sessions, 0) if p.sessions else "–",
                      hours(p.steam_minutes), p.steam_apps_played, p.accounts, p.nameless,
                      "da" if p.paid_included else "nu", _rated(p)] for p in people]
    sections.append(
        '<section class="card"><h2>Participanții</h2><p class="note">Câte un rând pentru fiecare export citit. '
        'Orele launcher-ului sunt de când și-a instalat fiecare launcher-ul; orele Steam sunt de-a lungul '
        'vieții conturilor marcate „Mine”. De aceea nu sunt adunate nicăieri. Evaluările (stelele date unei '
        'sesiuni) există de la formatul 3 al exportului; un export mai vechi nu are niciuna — nu i s-au cerut, '
        'ceea ce nu e zero.</p><div class="scroll">'
        + table(["", "Făcut pe", "Instalate", "Jucate sau marcate", "Ore launcher", "Sesiuni",
                 "Minute / sesiune", "Ore Steam", "Aplicații Steam jucate", "Conturi Steam",
                 "Fără nume", "Ce a plătit", "Evaluări"], overview_rows, 2, cls="nowrap")
        + "</div></section>")

    sections.append('<div class="pair">' + "".join([
        figure("Ore prin launcher", "Timpul măsurat de launcher, pe participant.",
               hbar_chart([(p.label, p.launcher_minutes / 60, f"{p.label}: {hours(p.launcher_minutes)} ore prin launcher")
                           for p in people], lambda v: num(v, 0)),
               table(["", "Ore", "Sesiuni"], [[p.label, hours(p.launcher_minutes), p.sessions] for p in people])),
        figure("Ore pe Steam", "Timpul Steam pe conturile marcate „Mine”, de-a lungul vieții lor.",
               hbar_chart([(p.label, p.steam_minutes / 60, f"{p.label}: {hours(p.steam_minutes)} ore pe Steam")
                           for p in people], lambda v: num(v, 0), slot=2),
               table(["", "Ore", "Conturi"], [[p.label, hours(p.steam_minutes), p.accounts] for p in people])),
    ]) + "</div>")

    keys = [s for s in comparison.SOURCE_ORDER if any(p.by_source.get(s) for p in people)]
    sections.append(figure(
        "De unde vin jocurile instalate", "Partea fiecărui magazin din jocurile instalate; „foldere” sunt jocurile "
        "puse de mână într-un folder.", stacked_chart([(p.label, p.by_source) for p in people], keys, SOURCE_WORDS),
        table([""] + [SOURCE_WORDS[k] for k in keys], [[p.label] + [p.by_source.get(k, 0) for k in keys] for p in people])))

    multiples = []
    hour_peak = max((v for p in people for v in p.hour_share.values()), default=0)
    day_peak = max((v for p in people for v in p.weekday_share.values()), default=0)
    for p in people:
        hours_chart = columns_chart([(str(h), p.hour_share.get(h, 0)) for h in range(24)], label_every=3,
                                    peak=hour_peak)
        days_chart = columns_chart([(WEEKDAYS_RO[d], p.weekday_share.get(d, 0)) for d in rules.ANALYSIS_WEEKDAYS],
                                   peak=day_peak)
        multiples.append(f'<div class="multiple"><h3>{esc(p.label)} · {p.sessions} sesiuni</h3>{hours_chart}{days_chart}</div>')
    sections.append(
        '<section class="card"><h2>Când se joacă</h2><p class="note">Sesiunile launcher-ului (Steam nu spune '
        'când): partea fiecărei ore din zi, apoi a fiecărei zile din săptămână, din minutele fiecăruia. Ora e '
        'cea locală, la care a început sesiunea.</p><div class="grid2">' + "".join(multiples) + "</div>"
        "<details><summary>Tabelul cu cifrele</summary><div class=\"scroll\">"
        + table(["Ora"] + [p.label for p in people],
                [[str(h)] + [num(p.hour_share.get(h, 0), 1) + "%" for p in people] for h in range(24)])
        + table(["Ziua"] + [p.label for p in people],
                [[WEEKDAYS_RO[d]] + [num(p.weekday_share.get(d, 0), 1) + "%" for p in people]
                 for d in rules.ANALYSIS_WEEKDAYS]) + "</div></details></section>")

    genres = comparison.genres_compared(people)
    genre_top = max((p.genre_share.get(g, 0) for p in people for g in genres), default=0)
    genre_multiples = []
    for p in people:
        if not p.genre_share:
            genre_multiples.append(f'<div class="multiple"><h3>{esc(p.label)}</h3><p class="note">Fără timp Steam.</p></div>')
            continue
        genre_multiples.append(f'<div class="multiple"><h3>{esc(p.label)}</h3>' + hbar_chart(
            [(g, p.genre_share.get(g, 0), f"{p.label} · {g}: {num(p.genre_share.get(g, 0), 1)}%") for g in genres],
            lambda v: num(v, 0) + "%", width=300, left=104, label_chars=14, top=genre_top) + "</div>")
    sections.append(
        '<section class="card"><h2>Genuri, după timpul Steam</h2><p class="note">Genurile Steam, ca parte din '
        'timpul Steam al fiecăruia. Un joc cu mai multe genuri își împarte minutele în mod egal între ele, așa că '
        'părțile unui participant fac împreună 100%. Arătate: genurile cu cea mai mare parte, la toți; toate '
        'graficele au aceeași scară.</p>'
        '<div class="grid2">' + "".join(genre_multiples) + "</div><details><summary>Tabelul cu cifrele</summary>"
        '<div class="scroll">' + table(["Gen"] + [p.label for p in people],
                                       [[g] + [num(p.genre_share.get(g, 0), 1) + "%" for p in people] for g in genres])
        + "</div></details></section>")

    if len(people) > 1:
        matrix = comparison.similarity(people)
        labels = [p.label for p in people]
        common = comparison.common_games(people)
        sections.append(figure(
            "Cât de asemănătoare sunt bibliotecile", "Indicele Jaccard pe jocurile jucate (cu număr Steam): câte au "
            "în comun, împărțit la câte au împreună. 0 = nimic în comun, 1 = aceleași jocuri.",
            heatmap(labels, matrix),
            table([""] + labels, [[a] + [("–" if matrix.get((a, b)) is None else num(matrix[(a, b)], 2)) for b in labels]
                                  for a in labels])))
        sections.append(
            '<section class="card"><h2>Jocuri jucate de mai mulți</h2><p class="note">Jocurile cu număr Steam jucate '
            f'de cel puțin doi participanți: {len(common)} în total, primele {rules.COMPARISON_COMMON_GAMES} '
            'după câți le-au jucat, apoi după ore (launcher și Steam, adunate doar aici, ca măsură a cât de jucat e '
            'jocul).</p><div class="scroll">'
            + table(["Joc", "Participanți", "Câți", "Ore în total"],
                    [[row["name"], ", ".join(row["participants"]), len(row["participants"]), hours(row["minutes"])]
                     for row in common[:rules.COMPARISON_COMMON_GAMES]], 2) + "</div></section>")

    top_rows = []
    for p in people:
        steam = "; ".join(f"{name} ({hours(m)} h)" for name, m in p.top_steam) or "–"
        launcher = "; ".join(f"{name} ({hours(m)} h)" for name, m in p.top_launcher) or "–"
        top_rows.append([p.label, steam, launcher])
    sections.append('<section class="card"><h2>Cele mai jucate</h2><p class="note">Primele '
                    f'{rules.COMPARISON_TOP_GAMES} ale fiecăruia, pe Steam și prin launcher. Un joc găsit doar într-un '
                    f'folder și nelegat de Steam apare ca „{comparison.NO_NAME}”.</p><div class="scroll">'
                    + table(["", "Pe Steam", "Prin launcher"], top_rows, 9) + "</div></section>")

    status_rows = [[p.label] + [p.status.get(s, 0) for s in STATUS_RO] + [p.favorites] for p in people]
    sections.append('<section class="card"><h2>Semnele puse jocurilor</h2><p class="note">Câte jocuri a marcat '
                    'fiecare ca fiind în curs, terminate sau abandonate, și câte au stea.</p>'
                    + table([""] + list(STATUS_RO.values()) + ["cu stea"], status_rows) + "</section>")

    paying = [p for p in people if p.paid_included]
    if paying:
        rows = [[p.label, p.purchases, "; ".join(f"{num(c / 100, 2)} {cur}" for cur, c in sorted(p.paid.items())) or "–"]
                for p in paying]
        sections.append('<section class="card"><h2>Ce au plătit</h2><p class="note">Doar participanții care au ales '
                        'să includă cumpărăturile; sumele nu sunt convertite între monede.</p>'
                        + table(["", "Cumpărături", "Total"], rows) + "</section>")

    files = "".join(f"<li>{esc(p.label)}: {esc(p.file)} (cod {esc(p.code)})</li>" for p in people)
    skipped = "".join(f"<li>{esc(name)}: {esc(why)}</li>" for name, why in loaded.skipped) or "<li>niciunul</li>"
    replaced = "".join(f"<li>{esc(old)}, înlocuit de {esc(new)} (același participant, mai nou)</li>"
                       for old, new in loaded.replaced)
    sections.append(
        '<section class="card"><h2>Fișierele</h2><p class="note">Numele fișierelor apar doar aici: dacă ai numit '
        'vreunul după cine ți l-a trimis, nu copia secțiunea aceasta în lucrare.</p><h3>Citite</h3>'
        f'<ul class="plain">{files}</ul><h3>Lăsate deoparte</h3><ul class="plain">{skipped}</ul>'
        + (f'<h3>Înlocuite</h3><ul class="plain">{replaced}</ul>' if replaced else "") + "</section>")

    sections.append(
        '<section class="card"><h2>Cum să citești cifrele</h2><ul class="plain">'
        "<li>Fiecare participant e un export anonim făcut de el, din Settings → Anonymous export; P1, P2, ... în "
        "ordinea zilei primului său fișier, apoi a codului; dintr-un participant cu mai multe fișiere contează cel "
        "mai nou, iar eticheta lui rămâne aceeași.</li>"
        "<li>Orele launcher-ului acoperă doar jocurile pornite din launcher, de la instalarea lui; jocurile Steam, "
        "Epic și Xbox nu sunt cronometrate de el.</li>"
        "<li>Orele Steam sunt cele ținute de Steam pe conturile marcate „Mine”, de-a lungul vieții lor.</li>"
        "<li>Jocurile găsite doar în foldere și nelegate de Steam nu au nume și nici număr Steam: intră în ore, nu "
        "și în asemănare sau în jocurile comune.</li>"
        "<li>Genurile sunt cele date de Steam; „Free to Play” sau „Early Access” sunt și ele genuri acolo.</li>"
        f"<li>{esc(_set_aside_line(people))}</li>"
        "<li>Sumele plătite nu sunt convertite între monede.</li></ul></section>")

    head = (f'<header><h1>Comparația bibliotecilor</h1><p class="meta">{len(people)} participanți · făcut pe '
            f'{today.isoformat()} · {esc(version.APP_NAME)} {esc(version.APP_VERSION)} · fișierele CSV sunt în '
            'același folder</p></header>')
    return ('<!doctype html><html lang="ro"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Comparația bibliotecilor</title><style>{_style()}</style></head>'
            f'<body><main class="viz-root"><div class="wrap">{head}{"".join(sections)}</div>'
            f'<div id="tip" role="tooltip"></div></main><script>{SCRIPT}</script></body></html>')


# -- the CSV files ---------------------------------------------------------------------------

def _csv(path: Path, head: list[str], rows: list[list]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out, delimiter=";")
        writer.writerow(head)
        for row in rows:
            writer.writerow([num(v, 1) if isinstance(v, float) else v for v in row])


def _game_stars(p, game: dict) -> list:
    """A game's ratings and mean stars for games.csv: empty for an export older than format 3 (never asked)."""
    if p.ratings is None:
        return ["", ""]
    stars = [r.get("stars") for r in game.get("ratings") or [] if isinstance(r, dict) and isinstance(r.get("stars"), int)]
    return [len(stars), round(sum(stars) / len(stars), 3) if stars else ""]


def write(loaded: comparison.Loaded, folder: Path, today: date | None = None) -> Path:
    """index.html and the CSV files into `folder`; the page's path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    people = loaded.participants
    index = folder / "index.html"
    index.write_text(page(loaded, today), encoding="utf-8")
    _csv(folder / "participants.csv",
         ["participant", "made_on", "app_version", "games", "installed"] + [f"installed_{s}" for s in comparison.SOURCE_ORDER]
         + ["launcher_minutes", "sessions", "session_minutes", "steam_minutes", "steam_apps_played", "steam_accounts",
            "nameless", "playing", "finished", "dropped", "favorites", "paid_included", "purchases", "paid",
            "observed_sessions", "observed_minutes", "ratings", "rated_games", "mean_stars"],
         [[p.label, p.data.get("made_on"), p.data.get("app_version"), p.games, p.installed]
          + [p.by_source.get(s, 0) for s in comparison.SOURCE_ORDER]
          + [p.launcher_minutes, p.sessions, p.session_minutes, p.steam_minutes, p.steam_apps_played, p.accounts,
             p.nameless, p.status.get("playing", 0), p.status.get("finished", 0), p.status.get("dropped", 0),
             p.favorites, int(p.paid_included), p.purchases,
             json.dumps(p.paid) if p.paid_included else "", p.observed_sessions, p.observed_minutes,
             "" if p.ratings is None else p.ratings, "" if p.rated_games is None else p.rated_games,
             "" if p.mean_stars is None else round(p.mean_stars, 3)] for p in people])
    _csv(folder / "games.csv",
         ["participant", "steam_appid", "name", "source", "installed", "launcher_minutes", "sessions",
          "session_minutes", "steam_minutes", "steam_accounts", "status", "favorite", "first_seen", "last_played", "genres",
          "ratings", "mean_stars"],
         [[p.label, g.get("steam_appid"), g.get("name"), g.get("source"), int(bool(g.get("installed"))),
           g.get("launcher_minutes"), g.get("sessions"), g.get("session_minutes"), g.get("steam_minutes"),
           g.get("steam_accounts"), g.get("status"), int(bool(g.get("favorite"))), g.get("first_seen"),
           g.get("last_played"), ", ".join(g.get("genres") or [])] + _game_stars(p, g)
          for p in people for g in p.data["games"]])
    _csv(folder / "steam_history.csv",
         ["participant", "steam_appid", "name", "minutes", "accounts", "last_played", "genres"],
         [[p.label, h.get("steam_appid"), h.get("name"), h.get("minutes"), h.get("accounts"), h.get("last_played"),
           ", ".join(h.get("genres") or [])] for p in people for h in p.data["steam"].get("history", [])])
    _csv(folder / "hours.csv", ["participant", "hour", "minutes", "share_percent"],
         [[p.label, h, int((p.data["sessions"].get("by_hour") or {}).get(str(h), 0)), float(p.hour_share.get(h, 0))]
          for p in people for h in range(24)])
    _csv(folder / "weekdays.csv", ["participant", "weekday", "minutes", "share_percent"],
         [[p.label, d, int((p.data["sessions"].get("by_weekday") or {}).get(d, 0)), float(p.weekday_share.get(d, 0))]
          for p in people for d in rules.ANALYSIS_WEEKDAYS])
    _csv(folder / "genres.csv", ["participant", "genre", "share_of_steam_time_percent"],
         [[p.label, g, float(share)] for p in people for g, share in p.genre_share.items()])
    matrix = comparison.similarity(people)
    labels = [p.label for p in people]
    _csv(folder / "similarity.csv", [""] + labels,
         [[a] + [("" if matrix.get((a, b)) is None else num(matrix[(a, b)], 3)) for b in labels] for a in labels])
    _csv(folder / "common_games.csv", ["steam_appid", "name", "participants", "count", "minutes"],
         [[row["steam_appid"], row["name"], ", ".join(row["participants"]), len(row["participants"]), row["minutes"]]
          for row in comparison.common_games(people)])
    log.info("comparison report: %s and 8 CSV files, %d participant(s)", index, len(people))
    return index
