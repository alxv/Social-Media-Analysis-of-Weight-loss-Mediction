#!/usr/bin/env python3
"""Download and aggregate FAERS data for weight-loss drugs via OpenFDA."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DRUG_LIST_PATH = BASE_DIR / "weight_loss_drug_list.csv"
AGG_CSV_PATH = DATA_DIR / "4.FAERS_data.csv"
EVENTS_JSON_PATH = DATA_DIR / "faers_weight_loss_events.json"
EVENTS_CSV_PATH = DATA_DIR / "faers_weight_loss_events.csv"
META_PATH = DATA_DIR / "faers_download_meta.json"

OPENFDA_URL = "https://api.fda.gov/drug/event.json"
PAGE_SIZE = 100
START_YEAR = 2015
END_YEAR = 2025

DOWNLOAD_DRUGS = [
    "semaglutide", "tirzepatide", "liraglutide", "orlistat", "phentermine",
    "naltrexone", "bupropion", "topiramate", "exenatide", "dulaglutide",
]
CAPS = {
    "semaglutide": 9000,
    "tirzepatide": 9000,
    "liraglutide": 6000,
    "orlistat": 5000,
    "phentermine": 3000,
    "naltrexone": 3000,
    "bupropion": 3000,
    "topiramate": 3000,
    "exenatide": 3000,
    "dulaglutide": 3000,
}


def log(msg: str) -> None:
    print(msg, flush=True)


def fetch_page(query: str, limit: int, skip: int) -> dict:
    params = {"search": query, "limit": limit, "skip": skip}
    for attempt in range(4):
        try:
            resp = requests.get(OPENFDA_URL, params=params, timeout=60)
            if resp.status_code == 404:
                return {"results": [], "meta": {"results": {"total": 0}}}
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
            log(f"  retry {attempt + 1}: {exc}")
    return {"results": []}


def build_search_queries(drug_list_df: pd.DataFrame, generic: str) -> list[str]:
    variants = drug_list_df.loc[
        drug_list_df["generic_name"].astype(str).str.lower() == generic.lower(), "variant"
    ].astype(str).str.strip().str.lower().unique()
    queries = []
    for v in variants:
        if not v or v == generic:
            continue
        if not v.isascii():
            continue
        queries.append(f'patient.drug.openfda.brand_name:"{v}"')
    queries.append(f'patient.drug.openfda.generic_name:"{generic}"')
    return list(dict.fromkeys(queries))


def process_event(event: dict, generic: str, counts: Counter, sample: list[dict], seen: set[str]) -> None:
    sid = event.get("safetyreportid")
    if not sid or sid in seen:
        return

    patient = event.get("patient", {})
    drugs = patient.get("drug", [])
    generic_found = False
    for drug in drugs:
        openfda = drug.get("openfda", {}) or {}
        names = [g.lower() for g in openfda.get("generic_name", [])]
        raw = str(drug.get("medicinalproduct", "")).lower()
        if generic in names or generic in raw:
            generic_found = True
            break
    if not generic_found:
        return

    reactions = [
        str(r.get("reactionmeddrapt", "")).strip().lower()
        for r in patient.get("reaction", [])
        if str(r.get("reactionmeddrapt", "")).strip()
    ]
    if not reactions:
        return

    receivedate = str(event.get("receivedate", ""))
    if len(receivedate) < 4 or not receivedate[:4].isdigit():
        return
    year = int(receivedate[:4])
    if year < START_YEAR or year > END_YEAR:
        return

    seen.add(sid)
    for reaction in reactions:
        counts[(generic, reaction, year)] += 1
    if len(sample) < 5000:
        sample.append(
            {
                "safetyreportid": sid,
                "receivedate": receivedate,
                "year": year,
                "generic": generic,
                "reactions": reactions,
            }
        )


def download_generic(generic: str, queries: list[str], counts: Counter, sample: list[dict], seen: set[str]) -> int:
    cap = CAPS.get(generic, 3000)
    added = 0
    for query in queries:
        if added >= cap:
            break
        try:
            meta = fetch_page(query, limit=1, skip=0)
        except requests.HTTPError as exc:
            log(f"  skipping bad query ({exc})")
            continue
        total = meta.get("meta", {}).get("results", {}).get("total", 0)
        if not total:
            continue
        fetch_n = min(total, cap - added, 25000)
        log(f"  {query[:65]}... total={total:,}, fetch={fetch_n:,}")
        skip = 0
        fetched = 0
        while fetched < fetch_n:
            try:
                page = fetch_page(query, limit=PAGE_SIZE, skip=skip)
            except requests.HTTPError as exc:
                log(f"  page skip={skip} failed: {exc}")
                break
            results = page.get("results", [])
            if not results:
                break
            before = len(seen)
            for raw in results:
                process_event(raw, generic, counts, sample, seen)
            fetched += len(results)
            added += len(seen) - before
            skip += PAGE_SIZE
            if len(results) < PAGE_SIZE:
                break
            time.sleep(0.08)
    return added


def save_outputs(counts: Counter, sample: list[dict], generics: list[str]) -> pd.DataFrame:
    agg_rows = [
        {"Drug": drug, "Year": year, "adverse Reaction": ae, "Count": count}
        for (drug, ae, year), count in sorted(counts.items())
    ]
    agg_df = pd.DataFrame(agg_rows)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    agg_df.to_csv(AGG_CSV_PATH, index=False)

    payload = {
        "metadata": {
            "source": "openFDA drug/event",
            "downloaded_generics": generics,
            "year_range": [START_YEAR, END_YEAR],
            "total_events_sampled": len(sample),
            "total_agg_rows": len(agg_df),
        },
        "results": sample,
    }
    with EVENTS_JSON_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    pd.DataFrame(sample).to_csv(EVENTS_CSV_PATH, index=False)
    meta = {
        "agg_rows": len(agg_df),
        "generics_with_data": sorted({d for d, _, _ in counts.keys()}),
        "year_min": int(agg_df["Year"].min()) if not agg_df.empty else None,
        "year_max": int(agg_df["Year"].max()) if not agg_df.empty else None,
        "total_reports": sum(counts.values()),
    }
    META_PATH.write_text(json.dumps(meta, indent=2))
    return agg_df


def load_existing_state() -> tuple[Counter, list[dict], set[str]]:
    counts: Counter = Counter()
    sample: list[dict] = []
    seen: set[str] = set()
    if AGG_CSV_PATH.exists():
        agg = pd.read_csv(AGG_CSV_PATH)
        for _, row in agg.iterrows():
            counts[(row["Drug"], row["adverse Reaction"], int(row["Year"]))] += int(row["Count"])
    if EVENTS_JSON_PATH.exists():
        with EVENTS_JSON_PATH.open() as fh:
            payload = json.load(fh)
        sample = payload.get("results", [])[:5000]
        seen = {str(x.get("safetyreportid")) for x in sample if x.get("safetyreportid")}
    return counts, sample, seen


def download_all(force: bool = False, append: bool = False) -> pd.DataFrame:
    if AGG_CSV_PATH.exists() and not force and not append:
        log(f"Using cached aggregated FAERS: {AGG_CSV_PATH}")
        return pd.read_csv(AGG_CSV_PATH)

    drug_list_df = pd.read_csv(DRUG_LIST_PATH)
    if append and AGG_CSV_PATH.exists():
        counts, sample, seen = load_existing_state()
        existing_drugs = {d for d, _, _ in counts.keys()}
        to_fetch = [g for g in DOWNLOAD_DRUGS if g not in existing_drugs]
        log(f"Appending FAERS for missing drugs: {to_fetch}")
    else:
        counts: Counter = Counter()
        sample: list[dict] = []
        seen: set[str] = set()
        to_fetch = DOWNLOAD_DRUGS

    for generic in to_fetch:
        log(f"\n=== {generic} ===")
        queries = build_search_queries(drug_list_df, generic)
        n = download_generic(generic, queries, counts, sample, seen)
        log(f"  collected {n:,} unique reports for {generic}")
        save_outputs(counts, sample, DOWNLOAD_DRUGS)

    agg_df = pd.read_csv(AGG_CSV_PATH)
    log(f"\nSaved {len(agg_df):,} aggregated rows to {AGG_CSV_PATH}")
    return agg_df


def main(force: bool = False, append: bool = False) -> None:
    agg = download_all(force=force, append=append)
    log("\n=== SUMMARY ===")
    log(f"Aggregated rows: {len(agg):,}")
    if not agg.empty:
        log(f"Year range: {agg['Year'].min()} – {agg['Year'].max()}")
        log("Reports by drug:")
        log(agg.groupby("Drug")["Count"].sum().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--append", action="store_true", help="Download only drugs missing from cache")
    args = parser.parse_args()
    try:
        main(force=args.force, append=args.append)
    except KeyboardInterrupt:
        log("Interrupted — partial cache retained if any drug completed.")
        sys.exit(1)
