#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scripts.sample_integration.opencode_webhook_handler import main

if __name__ == "__main__":
    main()
