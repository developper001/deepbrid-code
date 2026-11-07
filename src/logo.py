from __future__ import annotations

import tkinter as tk


def _paint_line(
    image: tk.PhotoImage,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str,
    width: int,
) -> None:
    x1, y1 = start
    x2, y2 = end
    steps = max(abs(x2 - x1), abs(y2 - y1), 1)
    radius = width // 2
    for step in range(steps + 1):
        x = round(x1 + (x2 - x1) * step / steps)
        y = round(y1 + (y2 - y1) * step / steps)
        image.put(
            color,
            to=(x - radius, y - radius, x + width - radius, y + width - radius),
        )


def create_brand_icon(master: tk.Misc, dark_theme: bool, size: int = 48) -> tk.PhotoImage:
    image = tk.PhotoImage(master=master, width=size, height=size)
    scale = size / 48
    bubble_color = "#7898ff" if dark_theme else "#3569f6"
    code_color = "#ffffff"
    slash_color = "#98f0c4" if dark_theme else "#a7ffcf"

    left, top, right, bottom, radius = (4, 4, 44, 36, 7)
    for y in range(round(top * scale), round(bottom * scale)):
        for x in range(round(left * scale), round(right * scale)):
            local_x = min(x / scale - left, right - x / scale)
            local_y = min(y / scale - top, bottom - y / scale)
            if (
                local_x >= radius
                or local_y >= radius
                or (local_x - radius) ** 2 + (local_y - radius) ** 2 <= radius**2
            ):
                image.put(bubble_color, (x, y))

    for y in range(round(33 * scale), round(44 * scale)):
        for x in range(round(13 * scale), round(25 * scale)):
            point_x, point_y = x / scale, y / scale
            edge_x = 25 - (point_y - 33) * (12 / 11)
            if point_x <= edge_x:
                image.put(bubble_color, (x, y))

    stroke = max(1, round(3 * scale))
    paths = (
        (((17, 12), (11, 19), (17, 26)), code_color),
        (((25, 26), (30, 12)), slash_color),
        (((33, 12), (39, 19), (33, 26)), code_color),
    )
    for points, color in paths:
        scaled = tuple((round(x * scale), round(y * scale)) for x, y in points)
        for start, end in zip(scaled, scaled[1:]):
            _paint_line(image, start, end, color, stroke)

    return image
