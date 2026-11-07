from __future__ import annotations

import tkinter as tk


_GLYPHS = {
    "<": ("00100", "01000", "10000", "10000", "10000", "01000", "00100"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    ">": ("00100", "00010", "00001", "00001", "00001", "00010", "00100"),
}


def create_brand_icon(master: tk.Misc, dark_theme: bool) -> tk.PhotoImage:
    image = tk.PhotoImage(master=master, width=48, height=48)
    bubble_color = "#7898ff" if dark_theme else "#3569f6"
    code_color = "#ffffff"
    slash_color = "#98f0c4" if dark_theme else "#a7ffcf"

    for y in range(4, 38):
        for x in range(4, 44):
            corner_x = min(x - 4, 43 - x)
            corner_y = min(y - 4, 37 - y)
            if corner_x >= 5 or corner_y >= 5 or (corner_x - 5) ** 2 + (corner_y - 5) ** 2 <= 25:
                image.put(bubble_color, (x, y))

    for y in range(35, 44):
        for x in range(9, 20):
            if x >= 18 - (y - 35):
                image.put(bubble_color, (x, y))

    for glyph_index, glyph in enumerate(("<", "/", ">")):
        color = slash_color if glyph == "/" else code_color
        x_offset = 7 + glyph_index * 12
        for row, pattern in enumerate(_GLYPHS[glyph]):
            for column, pixel in enumerate(pattern):
                if pixel == "1":
                    image.put(
                        color,
                        to=(
                            x_offset + column * 2,
                            12 + row * 2,
                            x_offset + column * 2 + 2,
                            12 + row * 2 + 2,
                        ),
                    )
    return image
