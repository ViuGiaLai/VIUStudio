import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
for p in [os.path.join(ROOT, 'app'), os.path.join(ROOT, 'ui'), ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)
