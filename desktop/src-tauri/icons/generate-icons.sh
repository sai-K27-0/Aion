#!/bin/bash
# Generate all required icon formats for Tauri from a source PNG
# Run this on macOS: ./generate-icons.sh source-icon.png
# 
# If no source is provided, generates a placeholder icon

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_ICON="${1:-}"

# Create a placeholder icon if none provided
if [ -z "$SOURCE_ICON" ] || [ ! -f "$SOURCE_ICON" ]; then
    echo "No source icon provided. Creating placeholder..."
    
    # Create a 512x512 placeholder using ImageMagick or Python
    if command -v convert &> /dev/null; then
        # ImageMagick available
        convert -size 512x512 xc:'#1A1A2E' \
            -fill '#4A90D9' -draw "polygon 256,80 400,432 320,432 280,320 232,320 192,432 112,432" \
            -fill '#00D9FF' -draw "circle 256,60 256,76" \
            icon.png
    elif command -v python3 &> /dev/null; then
        # Use Python with PIL
        python3 << 'PYTHON_SCRIPT'
from PIL import Image, ImageDraw

# Create 512x512 image with dark background
img = Image.new('RGBA', (512, 512), '#1A1A2E')
draw = ImageDraw.Draw(img)

# Draw stylized "A" 
points = [(256, 80), (400, 432), (320, 432), (280, 320), (232, 320), (192, 432), (112, 432)]
draw.polygon(points, fill='#4A90D9')

# Inner triangle cutout
inner_points = [(256, 200), (232, 280), (280, 280)]
draw.polygon(inner_points, fill='#1A1A2E')

# Accent dot
draw.ellipse([240, 44, 272, 76], fill='#00D9FF')

img.save('icon.png')
print("Created icon.png")
PYTHON_SCRIPT
    else
        echo "ERROR: Need ImageMagick or Python3 with PIL to generate placeholder"
        echo "Install with: brew install imagemagick"
        echo "Or: pip3 install Pillow"
        exit 1
    fi
    SOURCE_ICON="icon.png"
fi

echo "Generating icons from: $SOURCE_ICON"

# Generate PNG sizes
echo "Creating PNG variants..."
sips -z 32 32 "$SOURCE_ICON" --out 32x32.png
sips -z 128 128 "$SOURCE_ICON" --out 128x128.png
sips -z 256 256 "$SOURCE_ICON" --out "128x128@2x.png"
sips -z 512 512 "$SOURCE_ICON" --out icon.png

# Generate .icns for macOS
echo "Creating .icns..."
mkdir -p icon.iconset
sips -z 16 16 "$SOURCE_ICON" --out icon.iconset/icon_16x16.png
sips -z 32 32 "$SOURCE_ICON" --out icon.iconset/icon_16x16@2x.png
sips -z 32 32 "$SOURCE_ICON" --out icon.iconset/icon_32x32.png
sips -z 64 64 "$SOURCE_ICON" --out icon.iconset/icon_32x32@2x.png
sips -z 128 128 "$SOURCE_ICON" --out icon.iconset/icon_128x128.png
sips -z 256 256 "$SOURCE_ICON" --out icon.iconset/icon_128x128@2x.png
sips -z 256 256 "$SOURCE_ICON" --out icon.iconset/icon_256x256.png
sips -z 512 512 "$SOURCE_ICON" --out icon.iconset/icon_256x256@2x.png
sips -z 512 512 "$SOURCE_ICON" --out icon.iconset/icon_512x512.png
sips -z 1024 1024 "$SOURCE_ICON" --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
rm -rf icon.iconset

# Generate .ico for Windows (if ImageMagick available)
if command -v convert &> /dev/null; then
    echo "Creating .ico..."
    convert "$SOURCE_ICON" -define icon:auto-resize=256,128,64,48,32,16 icon.ico
else
    echo "Skipping .ico (install ImageMagick: brew install imagemagick)"
fi

echo ""
echo "Generated icons:"
ls -la *.png *.icns *.ico 2>/dev/null || true
echo ""
echo "Done! Icons are ready for Tauri build."
