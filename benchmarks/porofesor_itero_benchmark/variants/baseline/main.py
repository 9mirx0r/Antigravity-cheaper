"""Hextech Oracle (Aegis-LoL) - Desktop Application Launcher."""

import os
import sys

# Ensure package is importable from variants/baseline directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.desktop_app import DesktopApp


def main():
    """Launch Hextech Oracle Desktop Application."""
    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()
