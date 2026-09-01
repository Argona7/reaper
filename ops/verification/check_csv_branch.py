from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

module_path = Path(sys.argv[1]).resolve()
input_path = Path(sys.argv[2]).resolve()
spec = importlib.util.spec_from_file_location("reaper_csv_verification", module_path)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot load {module_path}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
items = module.CSVStatementParser().parse(input_path, account_last4="4242")
print(f"AMOUNTS={[item.amount_cents for item in items]}")
print(f"CONVENTIONS={[item.metadata['amount_convention'] for item in items]}")
