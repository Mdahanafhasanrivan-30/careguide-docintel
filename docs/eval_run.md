# Evaluation run, 2026-11-26 15:07 UTC

## Success and failure

| Measure | Value |
| --- | --- |
| Files evaluated | 60 (30 PDF, 30 scans) |
| Processed successfully (done) | 100.0% (60/60) |
| Failed | 0.0% (0/60) |
| Not finished when the run stopped | 0.0% (0/60) |
| Files that needed an automatic retry | 6.7% (4/60) |

## Field accuracy (AI version, compared with the label)

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
| line_items | 100.0% (30/30) | 96.7% (29/30) | 98.3% (59/60) |

| Overall | Fields correct | Documents with all 8 fields correct |
| --- | --- | --- |
| PDF | 100.0% (240/240) | 100.0% (30/30) |
| Scan | 98.3% (236/240) | 86.7% (26/30) |
| All | 99.2% (476/480) | 93.3% (56/60) |

### Every wrong field

- inv_004_scan.jpg: supplier_name
- inv_006_scan.jpg: supplier_name
- inv_019_scan.jpg: supplier_name
- inv_028_scan.jpg: currency
- inv_029_scan.jpg: line_items

## Processing time per stage (successful files)

| Stage | Files | Average | p50 | p95 | Max |
| --- | --- | --- | --- | --- | --- |
| parse | 60 | 317 ms | 91 ms | 718 ms | 1.4 s |
| extract | 60 | 11.4 s | 4.6 s | 28.3 s | 115.7 s |
| validate | 60 | 4 ms | 2 ms | 15 ms | 37 ms |
| index | 55 | 129 ms | 39 ms | 233 ms | 2.5 s |
| all four | 60 | 11.9 s | 5.2 s | 28.3 s | 115.8 s |
| parse, pdf only | 30 | 13 ms | 5 ms | 63 ms | 91 ms |
| parse, scan only | 30 | 621 ms | 571 ms | 842 ms | 1.4 s |

## This run (files uploaded now)

| Measure | Value |
| --- | --- |
| Files uploaded in this run | 46 |
| Upload to done, including queue wait | p50 165 s, p95 538 s, max 547 s |
| Wall time until all finished | 9.2 min (5.0 files per min, 1 worker) |

## Validation (needs_review on the AI version)

| Measure | Value |
| --- | --- |
| Planted-error invoices flagged | 100.0% (10/10) |
| Clean invoices flagged | 62.0% (31/50) |
| Clean invoices flagged for a reason other than a duplicate | 34.0% (17/50) |

Issue codes: duplicate_invoice 28, line_item_incomplete 7, currency_assumed 6, ambiguous_date 6, duplicate_number 6, line_amount_mismatch 2, tax_missing 2, total_mismatch 2, currency_missing 2, customer_name_missing 2, currency_unknown 1, line_items_sum_mismatch 1

