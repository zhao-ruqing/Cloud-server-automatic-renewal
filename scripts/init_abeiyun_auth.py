# -*- coding: utf-8 -*-
"""Abeiyun is retired; this script now inits the second Sanfeng account."""

import runpy
import sys
from pathlib import Path

print("Abeiyun is retired. Initializing sanfeng2 instead.")
script = Path(__file__).with_name("init_sanfeng_auth.py")
sys.argv = [str(script), "--provider", "sanfeng2"]
runpy.run_path(str(script), run_name="__main__")
