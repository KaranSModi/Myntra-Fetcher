"""Generate a sample JSON output file from the provided CSV."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.fetch_service import FetchService
from app.services.job_store import job_store


async def main() -> None:
    csv_path = Path("Products list.csv")
    service = FetchService()
    product_ids, warnings = service.parse_product_ids(csv_path.read_bytes())
    sample_ids = product_ids[:5]

    job = job_store.create_job(sample_ids)
    await service.process_job(job.job_id)

    output = {
        "job": job.to_summary(),
        "warnings": warnings,
        "results": [result.model_dump() for result in job.results],
    }

    out_path = Path("sample_output.json")
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(job.results)} results")


if __name__ == "__main__":
    asyncio.run(main())
