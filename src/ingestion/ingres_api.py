"""Client + crawler for the public (non-login) INGRES business-data endpoint.

Endpoint discovered by reading the INGRES Angular bundle (main.*.js):
    POST https://ingres.iith.ac.in/api/gec/getBusinessDataForUserOpen
The request body mirrors the portal's GIS-view URL params. `loctype` is the type of
the *parent* location; the response is the list of its children plus a `total` row:
    COUNTRY  -> states
    STATE    -> districts
    DISTRICT -> assessment units (block / taluk / mandal / firka / ...)

Every raw response is cached verbatim (gzipped JSON + request metadata) under
data/raw/ingres_api/<year>/ so the crawl is resumable and the processed DB is
reproducible from raw files without re-hitting the portal.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

API_URL = "https://ingres.iith.ac.in/api/gec/getBusinessDataForUserOpen"
COUNTRY_UUID = "ffce954d-24e1-494b-ba7e-0931d8ad6085"  # constants.COUNTRYUUID in the bundle


def load_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class IngresClient:
    raw_dir: Path
    sleep_s: float = 0.5
    retries: int = 4
    timeout_s: int = 180

    def path(self, year: str, loctype: str, uuid: str) -> Path:
        return self.raw_dir / year / f"{loctype}_{uuid}.json.gz"

    def fetch(self, year: str, loctype: str, uuid: str, parent_uuid: str, name: str) -> list[dict]:
        path = self.path(year, loctype, uuid)
        if path.exists():
            return load_raw(path)["response"]
        body = {
            "parentLocName": "INDIA", "locname": name, "loctype": loctype, "view": "admin",
            "locuuid": uuid, "year": year, "computationType": "normal", "component": "recharge",
            "period": "annual", "category": "safe", "mapOnClickParams": "false",
            "verificationStatus": 1, "approvalLevel": 1, "parentuuid": parent_uuid, "stateuuid": None,
        }
        req = urllib.request.Request(API_URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    resp = json.load(r)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                wait = 2 ** attempt * 5
                log.warning("fetch %s %s %s failed (%s); retry in %ss", year, loctype, name, e, wait)
                time.sleep(wait)
        else:
            raise RuntimeError(f"giving up on {year} {loctype} {name} {uuid}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump({"url": API_URL, "request": body,
                       "fetched_at": datetime.now(timezone.utc).isoformat(), "response": resp or []}, f)
        tmp.replace(path)  # atomic: an interrupted crawl never leaves a half-written cache file
        time.sleep(self.sleep_s)
        return resp or []


def children(rows: list[dict]) -> list[dict]:
    """Drop the synthetic aggregate row the API appends to every child list."""
    return [r for r in rows if r.get("locationName") != "total"]


def crawl_year(client: IngresClient, year: str, states: list[str] | None = None) -> dict[str, int]:
    """Country -> states -> districts -> assessment units for one assessment year."""
    counts = {"states": 0, "districts": 0, "units": 0}
    for st in children(client.fetch(year, "COUNTRY", COUNTRY_UUID, COUNTRY_UUID, "INDIA")):
        if states and st["locationName"].upper() not in states:
            continue
        counts["states"] += 1
        for d in children(client.fetch(year, "STATE", st["locationUUID"], COUNTRY_UUID, st["locationName"])):
            counts["districts"] += 1
            units = client.fetch(year, "DISTRICT", d["locationUUID"], st["locationUUID"], d["locationName"])
            counts["units"] += len(children(units))
        log.info("%s %s done: %s", year, st["locationName"], counts)
    return counts
