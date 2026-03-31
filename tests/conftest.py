"""pytest conftest -- add scripts/ to sys.path so dashboard_auth can be imported."""

import os
import sys

scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
