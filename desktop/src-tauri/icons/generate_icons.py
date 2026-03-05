"""Generate all Aion icon sizes using only Pillow (no Cairo dependency).
Draws a geometric/faceted abstract triangle directly."""
import subprocess
import sys

subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'Pillow', '-q'])

from PIL import Image, ImageDraw, ImageFilter
import os
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def lerp_color(c1, c2, t):
    """Linearly interpolate between two RGB(A) colors."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def draw_gradient_polygon(draw, img, points, color_top, color_bottom, bbox=None):
    """Fill a polygon with a vertical gradient."""
    # Create a mask for the polygon
    mask = Image.new('L', img.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.polygon(points, fill=255)

    # Determine bounding box
    if bbox is None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bbox = (min(xs), min(ys), max(xs), max(ys))

    y_min, y_max = bbox[1], bbox[3]
    height = y_max - y_min if y_max > y_min else 1

    # Create gradient image
    gradient = Image.new('RGBA', img.size, (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for y in range(int(y_min), int(y_max) + 1):
        t = (y - y_min) / height
        color = lerp_color(color_top, color_bottom, t)
        grad_draw.line([(0, y), (img.width, y)], fill=color)

    # Apply mask
    gradient.putalpha(mask)
    img.paste(gradient, (0, 0), gradient)


def create_icon(size):
    """Create the faceted triangle icon at a given size."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scale factor
    s = size / 512.0

    # Background circle
    margin = int(2 * s)
    # Dark background gradient (radial) - approximate with solid + lighter center
    bg_outer = (15, 17, 32, 255)  # #0F1120
    bg_inner = (30, 35, 64, 255)  # #1E2340

    # Draw background circle
    draw.ellipse([margin, margin, size - margin, size - margin], fill=bg_outer)

    # Lighter center for radial gradient effect
    center_r = int(180 * s)
    cx, cy = size // 2, size // 2
    for r in range(center_r, 0, -1):
        t = 1.0 - (r / center_r)
        color = lerp_color(bg_outer, bg_inner, t * 0.6)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Subtle glow behind triangle (cyan tint)
    glow_r = int(140 * s)
    glow_cy = int(270 * s)
    for r in range(glow_r, 0, -1):
        t = 1.0 - (r / glow_r)
        alpha = int(25 * t * t)
        glow_color = (0, 217, 255, alpha)
        glow_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)
        glow_draw.ellipse([cx - r, glow_cy - r, cx + r, glow_cy + r], fill=glow_color)
        img = Image.alpha_composite(img, glow_img)

    draw = ImageDraw.Draw(img)

    # Triangle vertices (scaled)
    top = (256 * s, 80 * s)
    bl = (136 * s, 400 * s)
    br = (376 * s, 400 * s)
    center = (256 * s, 320 * s)
    mid_bl = (196 * s, 400 * s)
    mid_br = (316 * s, 400 * s)

    # Face 1: Left face (darkest)
    face1_pts = [top, bl, center]
    face1_color = (30, 75, 128, 242)  # #1E4B80
    draw_gradient_polygon(draw, img, face1_pts,
                          (42, 95, 160, 242),   # lighter at top
                          (30, 75, 128, 242),   # darker at bottom
                          )

    # Face 2: Right face (medium)
    face2_pts = [top, br, center]
    draw_gradient_polygon(draw, img, face2_pts,
                          (58, 123, 200, 242),  # lighter blue
                          (42, 95, 160, 242),   # darker
                          )

    # Face 3: Bottom-left face (bright blue)
    face3_pts = [bl, center, mid_bl]
    draw_gradient_polygon(draw, img, face3_pts,
                          (91, 163, 230, 242),  # bright blue
                          (58, 123, 200, 242),
                          )

    # Face 4: Bottom-right face (brightest - cyan)
    face4_pts = [br, center, mid_br]
    draw_gradient_polygon(draw, img, face4_pts,
                          (0, 217, 255, 242),   # cyan
                          (74, 144, 217, 242),  # blue
                          )

    # Bottom center pieces
    face5_pts = [mid_bl, center, mid_br]
    draw_gradient_polygon(draw, img, face5_pts,
                          (74, 144, 217, 242),
                          (58, 123, 200, 242),
                          )

    face6_pts = [bl, mid_bl, center]  # small bottom-left
    draw.polygon([(int(p[0]), int(p[1])) for p in face6_pts],
                 fill=(42, 95, 160, 230))

    face7_pts = [br, mid_br, center]  # small bottom-right
    draw.polygon([(int(p[0]), int(p[1])) for p in face7_pts],
                 fill=(0, 180, 220, 230))

    # Edge lines (subtle white)
    edge_color = (255, 255, 255, 35)
    edge_width = max(1, int(1.2 * s))

    # Internal edges
    draw.line([_i(top), _i(center)], fill=(255, 255, 255, 38), width=edge_width)
    draw.line([_i(bl), _i(center)], fill=(255, 255, 255, 30), width=edge_width)
    draw.line([_i(br), _i(center)], fill=(255, 255, 255, 30), width=edge_width)
    draw.line([_i(mid_bl), _i(center)], fill=(255, 255, 255, 20), width=max(1, int(0.8 * s)))
    draw.line([_i(mid_br), _i(center)], fill=(255, 255, 255, 20), width=max(1, int(0.8 * s)))

    # Outer triangle edges (cyan tint)
    outer_color = (0, 217, 255, 60)
    draw.line([_i(top), _i(bl)], fill=outer_color, width=max(1, int(1.5 * s)))
    draw.line([_i(top), _i(br)], fill=outer_color, width=max(1, int(1.5 * s)))
    draw.line([_i(bl), _i(br)], fill=outer_color, width=max(1, int(1.5 * s)))

    # Top vertex glow point
    glow_r2 = max(2, int(4 * s))
    draw.ellipse([int(top[0]) - glow_r2, int(top[1]) - glow_r2,
                  int(top[0]) + glow_r2, int(top[1]) + glow_r2],
                 fill=(0, 217, 255, 200))

    return img


def _i(point):
    """Convert float point to int tuple."""
    return (int(point[0]), int(point[1]))


def create_ico(images, output_path):
    """Create .ico file from list of PIL Images."""
    images_sorted = sorted(images, key=lambda img: img.width, reverse=True)
    images_sorted[0].save(
        output_path,
        format='ICO',
        sizes=[(img.width, img.height) for img in images_sorted],
        append_images=images_sorted[1:]
    )
    print(f'  Created {os.path.basename(output_path)} (multi-resolution)')


def main():
    print('Generating Aion geometric triangle icons...')

    # Main icon sizes
    sizes = {
        'icon.png': 512,
        '32x32.png': 32,
        '128x128.png': 128,
        '128x128@2x.png': 256,
    }

    images = {}
    for name, size in sizes.items():
        img = create_icon(size)
        path = os.path.join(SCRIPT_DIR, name)
        img.save(path, 'PNG')
        images[size] = img
        print(f'  Created {name} ({size}x{size})')

    # Windows .ico
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_images = []
    for size in ico_sizes:
        if size in images:
            ico_images.append(images[size])
        else:
            ico_images.append(create_icon(size))
    create_ico(ico_images, os.path.join(SCRIPT_DIR, 'icon.ico'))

    # macOS .iconset
    iconset_dir = os.path.join(SCRIPT_DIR, 'icon.iconset')
    os.makedirs(iconset_dir, exist_ok=True)

    macos_sizes = {
        'icon_16x16.png': 16,
        'icon_16x16@2x.png': 32,
        'icon_32x32.png': 32,
        'icon_32x32@2x.png': 64,
        'icon_128x128.png': 128,
        'icon_128x128@2x.png': 256,
        'icon_256x256.png': 256,
        'icon_256x256@2x.png': 512,
        'icon_512x512.png': 512,
        'icon_512x512@2x.png': 1024,
    }

    print('\nmacOS iconset:')
    for name, size in macos_sizes.items():
        if size in images:
            img = images[size]
        else:
            img = create_icon(size)
            images[size] = img
        path = os.path.join(iconset_dir, name)
        img.save(path, 'PNG')
        print(f'  Created icon.iconset/{name} ({size}x{size})')

    print('\nAll icons generated successfully!')
    print('Note: Run "iconutil -c icns icon.iconset" on macOS to generate icon.icns')


if __name__ == '__main__':
    main()
