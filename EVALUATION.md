# Evaluation

Measured on 26 Nov 2026 with `backend/scripts/run_eval.py`, end to end through the running system (API → Redis queue → Celery worker → parse/OCR → Gemini `gemini-3.5-flash-lite`, prompt `extract_invoice_v3` → validation → indexing). One worker, Gemini free tier, on a Windows 11 + WSL2 laptop. The full report from the run is in [docs/eval_run.md](docs/eval_run.md); the test results are in [docs/test_results.txt](docs/test_results.txt).

## Summary

| Metric | Result |
| --- | --- |
| Extraction accuracy, 8 header fields | **99.2%** of fields (476/480): PDF 100.0%, scans 98.3% |
| Documents with all 8 fields correct | **93.3%** (56/60): PDF 100.0%, scans 86.7% |
| Document success rate | **100%** (60/60 reached `done`) |
| Document failure rate | **0%** (0/60); 4 files (6.7%) needed an automatic retry after a Gemini 503 |
| Processing time per file (work) | p50 **5.2 s**, p95 **28.3 s**, max 115.8 s |
| Throughput | 5.0 files per minute with one worker (46 new files in 9.2 min) |
| Planted errors flagged for review | **100%** (10/10) |
| Automated tests | 249 passed |

## Dataset

- 30 synthetic invoices generated with a fixed seed (`backend/scripts/make_dataset.py`), each as a text PDF and as a scanned JPG: **60 files**, with one answer key (`.json`) per invoice in `backend/eval_data`.
- Scans have noise, blur and rotation; 4 are hard scans (inv_007, 014, 021, 028).
- Planted errors, which the validator should flag: inv_005 missing tax, inv_009 printed total 1094.02 instead of 1084.02, inv_013 no currency, inv_017 no customer, inv_021 duplicate invoice number of inv_003.
- Other edge cases: ambiguous dates (inv_002, 014, 028), European number format (inv_025), several currencies (USD, EUR, GBP, BDT).

## Method

- **End to end.** The script uploads every file through `POST /api/v1/documents`, waits for the worker, then reads the stored result from Postgres. Files uploaded before are reused (same SHA-256), so they are not sent to Gemini twice.
- **The AI version is scored.** Every extraction is a numbered version (`source` = `ai` or `manual`); the latest AI version is scored, so manual corrections made in the UI do not count.
- **Correct** means equal to the answer key after normalising: amounts to the cent (`1.094,02` = `1094.02`), dates as dates, text ignoring case and spacing but not spelling. A field that is really absent is correct when the system also returns nothing.
- **Printed versus correct value.** The extractor is scored against what is printed (inv_009: 1094.02). Catching that the printed total is wrong is the validator's job, scored separately.
- **Time** comes from `processing_events`, which every stage writes with its duration. Percentiles are nearest-rank.
- Scoring rules are unit-tested in `backend/tests/test_eval_scoring.py`.

## Results

### Field accuracy

| Field | PDF | Scan | All |
| --- | --- | --- | --- |
| invoice_number | 100.0% (30/30) | 100.0% (30/30) | 100.0% (60/60) |
| invoice_date | 100.0% (30/30) | 100.0% (30/30) | 100.0% (60/60) |
| supplier_name | 100.0% (30/30) | 90.0% (27/30) | 95.0% (57/60) |
| customer_name | 100.0% (30/30) | 100.0% (30/30) | 100.0% (60/60) |
| subtotal | 100.0% (30/30) | 100.0% (30/30) | 100.0% (60/60) |
| tax | 100.0% (30/30) | 100.0% (30/30) | 100.0% (60/60) |
| total | 100.0% (30/30) | 100.0% (30/30) | 100.0% (60/60) |
| currency | 100.0% (30/30) | 96.7% (29/30) | 98.3% (59/60) |
| line items (row amounts) | 100.0% (30/30) | 96.7% (29/30) | 98.3% (59/60) |

These match the model-only measurement from Phase 2 (scans: supplier 90.0%, currency 96.7%), so the full pipeline adds no extraction errors of its own.

### Processing time per stage

| Stage | Files | Average | p50 | p95 | Max |
| --- | --- | --- | --- | --- | --- |
| parse, PDF | 30 | 13 ms | 5 ms | 63 ms | 91 ms |
| parse, scan (OCR) | 30 | 621 ms | 571 ms | 842 ms | 1.4 s |
| extract (Gemini) | 60 | 11.4 s | 4.6 s | 28.3 s | 115.7 s |
| validate | 60 | 4 ms | 2 ms | 15 ms | 37 ms |
| index (embeddings) | 55 | 129 ms | 39 ms | 233 ms | 2.5 s |
| all stages | 60 | 11.9 s | 5.2 s | 28.3 s | 115.8 s |

- **Gemini is almost all of the time.** At the median, extraction is 4.6 s of 5.2 s; parse, validate and index together are well under a second.
- **The long tail is retries.** The 115.7 s maximum is a call that hit Gemini 503s and waited between attempts. The average (11.4 s) is pulled up by these, which is why p50 and p95 are reported.
- **Scans cost OCR time**: about 0.6 s per page, versus 13 ms to read a PDF's text layer.
- Index shows 55 files: 5 older files were indexed by `scripts/reindex.py`, which does not write a processing event.

### Queue and throughput (46 files uploaded at once)

| Measure | Value |
| --- | --- |
| Upload to done, including queue wait | p50 165 s, p95 538 s, max 547 s |
| Wall time for the batch | 9.2 min (5.0 files per minute, 1 worker) |

With one worker the files wait in line, so upload-to-done grows with the batch size. The worker runs with concurrency 1 on purpose, to stay inside the free tier's 15 requests per minute.

### Validation

| Measure | Value |
| --- | --- |
| Planted-error invoices flagged | 100.0% (10/10) |
| Clean invoices flagged | 62.0% (31/50) |
| Clean invoices flagged for a reason other than a duplicate | 34.0% (17/50) |

Issue codes over all 60 files: duplicate_invoice 28, line_item_incomplete 7, currency_assumed 6, ambiguous_date 6, duplicate_number 6, line_amount_mismatch 2, tax_missing 2, total_mismatch 2, currency_missing 2, customer_name_missing 2, currency_unknown 1, line_items_sum_mismatch 1.

- Most flags on clean invoices are **duplicates by design**: every scan is the same invoice as its PDF, and the second copy is correctly flagged `duplicate_invoice`.
- `ambiguous_date` (6) is the three ambiguous-date invoices × 2 formats, which a person should confirm. `currency_assumed` (6) is invoices printing only `$`, where USD is an assumption.
- The flag rate is high on purpose: the system prefers asking a person over silently accepting a doubtful value.

## Errors

All 5 errors are on scans; every PDF field is correct.

| File | Field | Likely cause |
| --- | --- | --- |
| inv_004_scan.jpg | supplier_name | OCR misread of the supplier name |
| inv_006_scan.jpg | supplier_name | OCR misread of the supplier name |
| inv_019_scan.jpg | supplier_name | OCR misread of the supplier name |
| inv_028_scan.jpg | currency | Hard scan: currency symbol lost in OCR |
| inv_029_scan.jpg | line items | A line-item row misread |

The causes are attributed to OCR because the same invoices are 100% correct as PDFs; I have not yet checked the OCR text of each file.

## Limits

- **Small, synthetic dataset**: 60 files from one generator. The numbers show where the system is weak; they are not a promise for real customer documents.
- **Model confidence is not useful here**: Gemini reports close to 100% on almost every field, including wrong ones. The validation rules, not the confidence, catch problems.
- **Free tier**: 503s add long waits (max 115.7 s), and one worker limits throughput to about 5 files per minute.
- Excel and CSV files are supported by the pipeline but are not part of this labelled set.
- Semantic search chunks are not rebuilt after a manual correction.

## Reproduce

```bash
docker compose up -d
dcrun python scripts/run_eval.py > docs/eval_run.md          # upload, wait, score
dcrun python scripts/run_eval.py --no-upload > docs/eval_run.md  # score again, no Gemini calls
dcrun python -m pytest -v > docs/test_results.txt 2>&1
```