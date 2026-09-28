"""Crawl INGRES (country -> state -> district -> assessment unit) into data/raw/ingres_api/.

Resumable: already-cached responses are skipped.
    python scripts/crawl_ingres.py                      # years from configs/data.yaml
    python scripts/crawl_ingres.py --years 2016-2017 --states PUNJAB HARYANA
"""
import argparse
import logging
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ingestion.ingres_api import IngresClient, crawl_year  # noqa: E402

if __name__ == "__main__":
    cfg = yaml.safe_load((ROOT / "configs/data.yaml").read_text())
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", default=cfg["years"])
    ap.add_argument("--states", nargs="*", help="upper-case state names as INGRES spells them")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    client = IngresClient(ROOT / cfg["raw_dir"], **cfg["crawl"])
    for y in a.years:
        print(y, crawl_year(client, y, a.states), flush=True)
