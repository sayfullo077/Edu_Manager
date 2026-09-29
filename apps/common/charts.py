"""Serverda chiziladigan SVG grafiklar uchun geometriya (JS kutubxonasiz, CSP'ga mos).

Shablon faqat tayyor koordinatalarni chizadi; ranglar CSS tokenlaridan olinadi (tungi rejimda ham to'g'ri).
"""

import math
from dataclasses import dataclass


def _nice_max(value: float, ticks: int = 4) -> float:
    if value <= 0:
        return ticks
    raw = value / ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return step * ticks


def _smooth_path(pts: list[tuple[float, float]]) -> str:
    """Catmull-Rom → kubik Bezier: nuqtalardan o'tuvchi silliq chiziq (monoton segmentlar)."""
    if not pts:
        return ""
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        lo, hi = min(p1[1], p2[1]), max(p1[1], p2[1])
        # Nazorat nuqtalari segment chegarasida: egri chiziq "o'tib ketmaydi" (masalan, noldan pastga).
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(hi, max(lo, p1[1] + (p2[1] - p0[1]) / 6)))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(hi, max(lo, p2[1] - (p3[1] - p1[1]) / 6)))
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)


@dataclass
class LineChart:
    width: int
    height: int
    left: int
    right: int
    top: int
    bottom: int
    labels: list
    columns: list
    x_end: float
    y_base: float
    primary: dict
    secondary: dict
    y_ticks: list
    y2_ticks: list


def dual_line_chart(data: list[dict], primary: str, secondary: str, *, width=640, height=260) -> LineChart:
    left, right, top, bottom = 48, 40, 16, 32
    plot_w, plot_h = width - left - right, height - top - bottom
    n = max(len(data) - 1, 1)
    xs = [left + plot_w * i / n for i in range(len(data))]

    def series(key):
        mx = _nice_max(max((d[key] for d in data), default=0))
        pts = [(x, top + plot_h * (1 - d[key] / mx)) for x, d in zip(xs, data, strict=True)]
        path = _smooth_path(pts)
        area = f"{path} L{xs[-1]:.1f},{top + plot_h:.1f} L{xs[0]:.1f},{top + plot_h:.1f} Z" if pts else ""
        points = [{"x": round(x, 1), "y": round(y, 1), "value": d[key], "label": d["label"]}
                  for (x, y), d in zip(pts, data, strict=True)]
        ticks = [{"y": round(top + plot_h * (1 - i / 4), 1), "value": round(mx * i / 4)} for i in range(5)]
        return {"path": path, "area": area, "points": points}, ticks

    p, p_ticks = series(primary)
    s, s_ticks = series(secondary)
    labels = [{"x": round(x, 1), "text": d["label"]} for x, d in zip(xs, data, strict=True)]
    # Kursor uchun ko'rinmas ustunlar: har bir nuqta atrofidagi butun balandlik (qo'shni nuqtalar o'rtasigacha).
    columns = []
    for i, x in enumerate(xs):
        x0 = left if i == 0 else (xs[i - 1] + x) / 2
        x1 = width - right if i == len(xs) - 1 else (x + xs[i + 1]) / 2
        columns.append({"i": i, "x": round(x, 1), "x0": round(x0, 1), "w": round(x1 - x0, 1),
                        "y": p["points"][i]["y"], "label": data[i]["label"]})
    return LineChart(width, height, left, right, top, bottom, labels, columns, width - right, height - bottom,
                     p, s, p_ticks, s_ticks)


def donut(segments: list[tuple[str, float, str]], *, radius=70, stroke=22) -> dict:
    """segments: [(nomi, qiymat, css_rang)]. stroke-dasharray bilan chiziladi."""
    circumference = 2 * math.pi * radius
    total = sum(v for _, v, _ in segments) or 1
    offset, x, arcs = 0.0, 0.0, []
    for label, value, color in segments:
        length = circumference * value / total
        share = value * 100 / total
        arcs.append({"label": label, "value": value, "color": color, "percent": round(share),
                     "x": f"{x:.2f}", "w": f"{share:.2f}",  # gorizontal ustunli diagramma uchun
                     "dash": f"{length:.2f} {circumference - length:.2f}", "offset": f"{-offset:.2f}"})
        offset += length
        x += share
    size = (radius + stroke) * 2
    return {"arcs": arcs, "radius": radius, "stroke": stroke, "size": size, "center": size / 2,
            "empty": sum(v for _, v, _ in segments) == 0}


def ring(percent: float, *, radius=38, stroke=8) -> dict:
    """Bitta foizli halqa (byudjet ishlatilishi)."""
    circumference = 2 * math.pi * radius
    p = max(0.0, min(100.0, float(percent)))
    size = (radius + stroke) * 2
    return {"radius": radius, "stroke": stroke, "size": size, "center": size / 2,
            "dash": f"{circumference * p / 100:.2f} {circumference:.2f}"}
