#!/usr/bin/env python3
"""
Generate Aion app icons for all platforms.
Run: python generate-icons.py [source_icon.png]

If no source is provided, generates a placeholder Aion logo.
Requires: pip install Pillow
"""

import sys
import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow library required.")
    print("Install with: pip install Pillow")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent


def create_placeholder_icon(size=512):
    """Create a stylized 'A' logo for Aion."""
    img = Image.new('RGBA', (size, size), (26, 26, 46, 255))  # #1A1A2E
    draw = ImageDraw.Draw(img)
    
    # Scale factor
    s = size / 512
    
    # Stylized "A" shape
    a_points = [
        (256 * s, 80 * s),    # Top point
        (400 * s, 432 * s),   # Bottom right outer
        (320 * s, 432 * s),   # Bottom right inner
        (280 * s, 320 * s),   # Right notch
        (232 * s, 320 * s),   # Left notch
        (192 * s, 432 * s),   # Bottom left inner
        (112 * s, 432 * s),   # Bottom left outer
    ]
    draw.polygon(a_points, fill=(74, 144, 217, 255))  # #4A90D9
    
    # Inner triangle cutout
    inner_points = [
        (256 * s, 200 * s),
        (232 * s, 280 * s),
        (280 * s, 280 * s),
    ]
    draw.polygon(inner_points, fill=(26, 26, 46, 255))  # #1A1A2E
    
    # Accent dot at top
    dot_radius = 16 * s
    dot_center = (256 * s, 60 * s)
    draw.ellipse([
        dot_center[0] - dot_radius,
        dot_center[1] - dot_radius,
        dot_center[0] + dot_radius,
        dot_center[1] + dot_radius
    ], fill=(0, 217, 255, 255))  # #00D9FF
    
    return img


def resize_icon(source, size):
    """Resize an icon to the specified size."""
    return source.resize((size, size), Image.Resampling.LANCZOS)


def generate_ico(source, output_path):
    """Generate Windows .ico file with multiple sizes."""
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    icons = [resize_icon(source, size[0]) for size in sizes]
    icons[0].save(output_path, format='ICO', sizes=sizes)


def generate_icns(source, output_path):
    """Generate macOS .icns file."""
    # Create iconset directory
    iconset_dir = output_path.with_suffix('.iconset')
    iconset_dir.mkdir(exist_ok=True)
    
    # Required sizes for macOS iconset
    icon_sizes = [
        ('icon_16x16.png', 16),
        ('icon_16x16@2x.png', 32),
        ('icon_32x32.png', 32),
        ('icon_32x32@2x.png', 64),
        ('icon_128x128.png', 128),
        ('icon_128x128@2x.png', 256),
        ('icon_256x256.png', 256),
        ('icon_256x256@2x.png', 512),
        ('icon_512x512.png', 512),
        ('icon_512x512@2x.png', 1024),
    ]
    
    for filename, size in icon_sizes:
        icon = resize_icon(source, size)
        icon.save(iconset_dir / filename, format='PNG')
    
    # Convert to icns using iconutil (macOS only)
    if sys.platform == 'darwin':
        import subprocess
        try:
            subprocess.run(['iconutil', '-c', 'icns', str(iconset_dir)], check=True)
            # Clean up iconset directory
            import shutil
            shutil.rmtree(iconset_dir)
            print(f"  Created: {output_path}")
        except subprocess.CalledProcessError as e:
            print(f"  Warning: iconutil failed - {e}")
            print(f"  Iconset saved to: {iconset_dir}")
    else:
        print(f"  Iconset saved to: {iconset_dir}")
        print(f"  Run on macOS: iconutil -c icns {iconset_dir}")


def main():
    os.chdir(SCRIPT_DIR)
    
    # Check for source icon argument
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        print(f"Loading source icon: {sys.argv[1]}")
        source = Image.open(sys.argv[1]).convert('RGBA')
        # Ensure it's square and at least 1024x1024
        if source.size[0] != source.size[1]:
            size = max(source.size)
            new_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            offset = ((size - source.size[0]) // 2, (size - source.size[1]) // 2)
            new_img.paste(source, offset)
            source = new_img
        if source.size[0] < 1024:
            source = source.resize((1024, 1024), Image.Resampling.LANCZOS)
    else:
        print("Creating placeholder Aion icon...")
        source = create_placeholder_icon(1024)
    
    print("Generating icons...")
    
    # Generate PNG files for Tauri
    print("  Creating PNG files...")
    resize_icon(source, 512).save('icon.png', format='PNG')
    resize_icon(source, 32).save('32x32.png', format='PNG')
    resize_icon(source, 128).save('128x128.png', format='PNG')
    resize_icon(source, 256).save('128x128@2x.png', format='PNG')
    print("  Created: icon.png, 32x32.png, 128x128.png, 128x128@2x.png")
    
    # Generate Windows ICO
    print("  Creating Windows icon...")
    generate_ico(source, Path('icon.ico'))
    print("  Created: icon.ico")
    
    # Generate macOS ICNS
    print("  Creating macOS icon...")
    generate_icns(source, Path('icon.icns'))
    
    print("")
    print("Done! Icons generated successfully.")
    print("")
    print("Files created:")
    for f in sorted(SCRIPT_DIR.glob('*')):
        if f.suffix in ['.png', '.ico', '.icns'] or f.suffix == '.iconset':
            print(f"  - {f.name}")


if __name__ == '__main__':
    main()
