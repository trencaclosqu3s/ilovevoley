"""Script to generate high-resolution shortcut icons for PWA manifest.

Renders at 768x768 and downsamples with Lanczos to 192x192 for crisp anti-aliasing.
"""
import os
from PIL import Image, ImageDraw

BG_COLOR = (1, 105, 111, 255)  # #01696f
FG_COLOR = (255, 255, 255, 255)
ACCENT_COLOR = (255, 255, 255, 220)

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'ilovevoley',
    'static',
    'images',
    'icons'
)


def create_base_canvas():
    return Image.new('RGBA', (768, 768), BG_COLOR)


def generate_matches_icon():
    im = create_base_canvas()
    draw = ImageDraw.Draw(im)

    # Binder loops at top
    draw.rounded_rectangle([250, 140, 290, 250], radius=18, fill=FG_COLOR)
    draw.rounded_rectangle([478, 140, 518, 250], radius=18, fill=FG_COLOR)

    # Calendar outer box
    draw.rounded_rectangle([150, 200, 618, 620], radius=52, outline=FG_COLOR, width=28)

    # Calendar header separator line
    draw.line([(150, 320), (618, 320)], fill=FG_COLOR, width=28)

    # Calendar day grid dots (3 rows x 3 columns)
    cols = [250, 384, 518]
    rows = [390, 470, 550]
    for r_idx, r in enumerate(rows):
        for c_idx, c in enumerate(cols):
            if r_idx == 1 and c_idx == 1:
                # Highlight center dot
                draw.circle((c, r), radius=26, fill=FG_COLOR)
            else:
                draw.circle((c, r), radius=18, fill=FG_COLOR)

    # Downsample
    final_im = im.resize((192, 192), Image.Resampling.LANCZOS)
    path = os.path.join(OUTPUT_DIR, 'shortcut-matches.png')
    final_im.save(path, 'PNG')
    print(f'Generated {path}')


def generate_photos_icon():
    im = create_base_canvas()
    draw = ImageDraw.Draw(im)

    # Top viewfinder / flash prism
    draw.rounded_rectangle([270, 180, 420, 250], radius=24, outline=FG_COLOR, width=28)

    # Camera body
    draw.rounded_rectangle([150, 240, 618, 600], radius=56, outline=FG_COLOR, width=28)

    # Lens outer circle
    draw.circle((384, 425), radius=110, outline=FG_COLOR, width=28)

    # Lens inner circle
    draw.circle((384, 425), radius=55, outline=FG_COLOR, width=20)

    # Flash dot
    draw.circle((535, 315), radius=24, fill=FG_COLOR)

    # Downsample
    final_im = im.resize((192, 192), Image.Resampling.LANCZOS)
    path = os.path.join(OUTPUT_DIR, 'shortcut-photos.png')
    final_im.save(path, 'PNG')
    print(f'Generated {path}')


def generate_notifications_icon():
    im = create_base_canvas()
    draw = ImageDraw.Draw(im)

    # Bell top handle
    draw.arc([354, 150, 414, 230], start=180, end=0, fill=FG_COLOR, width=26)

    # Bell body
    # Using polygon with curved points or arc + trapezoid
    # Top dome: 300 to 468, y=210 to 360
    # Flare out: down to x=174 to 594 at y=520
    bell_points = [
        (330, 220),
        (438, 220),
        (460, 290),
        (475, 380),
        (560, 490),
        (580, 525),
        (188, 525),
        (208, 490),
        (293, 380),
        (308, 290),
    ]
    draw.polygon(bell_points, outline=FG_COLOR, width=28)

    # Rim rounded bar
    draw.rounded_rectangle([150, 515, 618, 550], radius=16, fill=FG_COLOR)

    # Clapper
    draw.chord([344, 545, 424, 625], start=0, end=180, fill=FG_COLOR)

    # Alert notification dot at top right
    draw.circle((560, 200), radius=34, fill=FG_COLOR)

    # Downsample
    final_im = im.resize((192, 192), Image.Resampling.LANCZOS)
    path = os.path.join(OUTPUT_DIR, 'shortcut-notifications.png')
    final_im.save(path, 'PNG')
    print(f'Generated {path}')


if __name__ == '__main__':
    generate_matches_icon()
    generate_photos_icon()
    generate_notifications_icon()
