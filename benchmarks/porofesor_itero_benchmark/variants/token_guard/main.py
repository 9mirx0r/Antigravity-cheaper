import os
import sys

# Ensure package is importable from variants/token_guard directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.desktop_app import HextechOracleApp


def main():
    """Launch Hextech Oracle Desktop Application."""
    app = HextechOracleApp()
    app.run()


if __name__ == "__main__":
    main()
