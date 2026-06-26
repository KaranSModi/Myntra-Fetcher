# Myntra Fetcher

A production-oriented tool that reads a CSV of Myntra `product_id` values, fetches public product page data, returns sponsored category ads, and optionally checks delivery for major Indian cities.

For system design, data flows, and component responsibilities, see [architecture.md](architecture.md).

## Features

- CSV upload with `product_id` column
- Per-product structured JSON output
- Core fields: title, description, images, rating, rating count, category
- First 3 sponsored (`AD`) category results with rating and price
- Optional delivery checks for Mumbai, Bangalore, Delhi, Ahmedabad, and Kolkata
- Hosted web UI with progress, results table, and JSON download
- Robust per-product error handling (`success`, `partial`, `failed`)

## How to run

### Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

### Docker

```bash
docker compose up --build
```

### Generate sample output

```bash
python scripts/generate_sample_output.py
```

This writes `sample_output.json` for the first 5 products in `Products list.csv`.

## API

### `POST /api/v1/jobs`

Upload a CSV file as `multipart/form-data` with field name `file`.

### `GET /api/v1/jobs`

List recently saved fetch jobs (persisted on disk).

### `GET /api/v1/jobs/{job_id}`

Poll job status and results.

### `GET /api/v1/jobs/{job_id}/download`

Download completed job output as JSON.

### `POST /api/v1/jobs/{job_id}/retry-failed`

Re-fetch products that failed or were partial in a completed job. Query param `include_partial` (default `true`) controls whether partial results are retried. Returns immediately and processes in the background; poll `GET /api/v1/jobs/{job_id}` for progress.

## Approach

### Product pages

Myntra exposes product data in server-rendered HTML via `window.__myx.pdpData`.

The tool fetches:

```text
https://www.myntra.com/{product_id}
```

No product slug is required.

### Category ads

The breadcrumb category (for example `Handbags`) maps to a listing page such as:

```text
https://www.myntra.com/handbags
```

Sponsored results are read from `searchData.results.plaProducts`, which corresponds to the `AD` badge shown in the UI. Only the first 3 sponsored results are returned.

Category slug resolution priority:

1. `crossLinks` URL slug (for example `handbags?f=Gender:women`)
2. Fallback to `analytics.articleType`

Category pages are cached per slug during a job to reduce duplicate requests.

### Delivery checks

After loading the PDP once, the tool reuses session cookies and calls:

- `POST /gateway/v1/user/locationContext`
- `POST /gateway/v2/serviceability/check`

The delivery date shown in the UI (for example `Get it by Sat, Jun 27`) comes from the v2 response field `promiseDate` (epoch milliseconds) inside a `serviceType: DELIVERY` entry. The v3 endpoint only confirms serviceability and does not return the promise date.

Configured pincodes:

| City | Pincode |
|------|---------|
| Mumbai | 400072 |
| Bangalore | 560001 |
| Delhi | 110006 |
| Ahmedabad | 380054 |
| Kolkata | 700001 |

Delivery output includes `serviceable`, `delivery_text`, and `estimated_days` when available.

### Reliability

- Request throttling and retry with backoff (shared for PDP HTML and cookie-based fetches)
- Limited concurrency (default: 3)
- Per-product isolation so one failure does not stop the job
- Retry failed/partial products via `POST /api/v1/jobs/{job_id}/retry-failed`
- Explicit warnings for missing fields and partial category ad sets

## Assumptions

1. Input CSV contains a `product_id` column with numeric Myntra style IDs.
2. Duplicate IDs are deduplicated once per job.
3. Category ads are sourced from the category listing page derived from PDP metadata.
4. `plaProducts` with `isPLA: true` represent sponsored `AD` results.
5. Fewer than 3 sponsored ads may be available for some categories.
6. Delivery checks depend on Myntra gateway session cookies from the PDP request.

## Scoped in

- CSV ingest and validation
- PDP extraction for all required core fields
- Category ad extraction (first 3 sponsored results)
- Delivery checks for 5 provided pincodes
- Web UI, JSON API, Docker setup
- Saved run history (jobs persist under `data/jobs/` and reload after refresh)
- Unit tests for parser, mapper, and CSV parsing
- Sample output generation script

## Scoped out / next steps

- Persistent database or job history beyond process memory
- Proxy rotation or distributed scraping
- Seller-authenticated Myntra APIs
- Full end-to-end browser automation for every request
- Running the entire 100-product CSV in CI by default (rate-limit sensitive)

With more time, I would add:

- Redis-backed job queue for long-running batches
- HTML fixture-based integration tests
- Stronger delivery date parsing from additional gateway fields
- Category slug fallback heuristics from breadcrumb URLs
- Result caching by `product_id`

## Known limitations

- Myntra may rate-limit or block aggressive automated traffic.
- Delivery estimates may return only serviceability without explicit day counts for some products.
- Sponsored ad inventory is dynamic and can vary by location/time.
- Gateway APIs require cookies from the initial PDP visit.

## Project structure

See [architecture.md](architecture.md) for a detailed breakdown of layers, request flows, and extension points.

```text
architecture.md
app/
  api/v1/endpoints/jobs.py
  core/config.py
  integrations/myntra/
    client.py
    parser.py
    mapper.py
    exceptions.py
  services/
    fetch_service.py
    job_store.py
  static/
  main.py
scripts/generate_sample_output.py
tests/
```

## Testing

```bash
pytest
```

## Example result shape

```json
{
  "product_id": "35512522",
  "status": "partial",
  "product": {
    "product_id": "35512522",
    "title": "EcoRight Eve Women Textured Crossbody Shoulder Bag",
    "description": "Coffee brown textured sling bag...",
    "images": ["https://assets.myntassets.com/..."],
    "rating": 4.54,
    "rating_count": 166,
    "category": "Accessories > Bags > Handbags",
    "category_slug": "handbags",
    "product_url": "https://www.myntra.com/35512522",
    "category_url": "https://www.myntra.com/handbags"
  },
  "category_ads": [
    {
      "product_id": "23102450",
      "title": "MIRAGGIO Freya Black Shoulder Bag",
      "price": 2199,
      "rating": 4.76,
      "is_sponsored": true
    }
  ],
  "delivery": [
    {
      "city": "Mumbai",
      "pincode": "400072",
      "serviceable": true,
      "delivery_text": "Serviceable"
    }
  ],
  "errors": [],
  "meta": {
    "fetched_at": "2026-06-25T12:00:00+00:00",
    "category_slug_used": "handbags"
  }
}
```
