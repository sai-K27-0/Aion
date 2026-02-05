#!/bin/bash
# Aion Desktop - macOS Setup Script
# Run this on a Mac to set up the development environment and build

set -e

echo "========================================"
echo "  Aion Desktop - macOS Setup"
echo "========================================"
echo ""

# Check for Xcode Command Line Tools
echo "Checking Xcode Command Line Tools..."
if ! xcode-select -p &> /dev/null; then
    echo "Installing Xcode Command Line Tools..."
    xcode-select --install
    echo "Please complete the installation and run this script again."
    exit 1
fi
echo "✓ Xcode Command Line Tools installed"

# Check for Homebrew
echo "Checking Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
echo "✓ Homebrew installed"

# Check for Rust
echo "Checking Rust..."
if ! command -v rustc &> /dev/null; then
    echo "Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi
echo "✓ Rust installed ($(rustc --version))"

# Add Rust targets for universal binary
echo "Adding Rust targets for universal macOS binary..."
rustup target add aarch64-apple-darwin
rustup target add x86_64-apple-darwin
echo "✓ Rust targets configured"

# Check for Node.js
echo "Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "Installing Node.js via Homebrew..."
    brew install node
fi
echo "✓ Node.js installed ($(node --version))"

# Install ImageMagick for icon generation
echo "Checking ImageMagick..."
if ! command -v convert &> /dev/null; then
    echo "Installing ImageMagick..."
    brew install imagemagick
fi
echo "✓ ImageMagick installed"

# Navigate to desktop directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(dirname "$SCRIPT_DIR")"
cd "$DESKTOP_DIR"

echo ""
echo "Setting up project..."
echo ""

# Install npm dependencies
echo "Installing npm dependencies..."
npm install

# Generate icons if not present
if [ ! -f "src-tauri/icons/icon.icns" ]; then
    echo "Generating icons..."
    cd src-tauri/icons
    
    # If iconset exists, convert it to icns
    if [ -d "icon.iconset" ]; then
        echo "Converting iconset to icns..."
        iconutil -c icns icon.iconset
        rm -rf icon.iconset
    elif [ -f "generate-icons.py" ]; then
        echo "Running Python icon generator..."
        python3 generate-icons.py
        # Convert iconset to icns
        if [ -d "icon.iconset" ]; then
            iconutil -c icns icon.iconset
            rm -rf icon.iconset
        fi
    elif [ -f "generate-icons.sh" ]; then
        chmod +x generate-icons.sh
        ./generate-icons.sh
    else
        echo "Warning: No icon generator found. Using default icons."
    fi
    cd ../..
fi
echo "✓ Icons ready"

echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "To build the .dmg for macOS:"
echo ""
echo "  npm run tauri:build:macos"
echo ""
echo "The .dmg will be in:"
echo "  src-tauri/target/universal-apple-darwin/release/bundle/dmg/"
echo ""
echo "For development mode:"
echo ""
echo "  npm run tauri:dev"
echo ""
