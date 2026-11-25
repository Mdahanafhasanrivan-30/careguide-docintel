# Phase 0 notes (my own words) (22 nov 2026)

1. I have set up the wsl and integrated it ,checked the version,integrated ubuntu and installed docker desktop.
2. I would have used virtual machine but docker desktop is far more valuable because of its speed, device independency and virual host kernel . I can keep a package of all elements of my project.
3. I ran all commands in linux to set up initial backend,api,venv and database and build the docket to up the initial project. checked the testing criterias for security myself and updated readme file.
## Phase 1 summary: document processing (23 Nov 2026)

In Phase 1 I built the part of the system that reads a file and turns it into text. It accepts PDFs, images (including multi-page TIFF), Excel files and CSVs, and it always returns the same result: text page by page, how each page was read (text layer, OCR or table), the OCR confidence, and any warnings.

How it works: the file type is detected from the file's content, not its name, so a PNG renamed to .pdf is still treated as an image. For PDFs, each page uses the built-in text if there is any, and falls back to OCR (Tesseract, after cleaning the image with OpenCV) only for scanned pages. Bad inputs, such as empty, corrupt, password-protected, too large or unsupported files, give a clear typed error and not a crash. I also added limits against huge images and TIFFs with too many frames.

What I tested: I wrote 24 tests with generated sample files (digital and scanned PDF, clean, skewed and low-res images, multi-page TIFF, CSV and Excel). All 24 pass in about 5 seconds. A command-line tool lets me check any file by hand.

What I found: a digital PDF took 19 ms, while the scanned version took about 1.6 s, so using the text layer first really saves time. OCR was good but not perfect ("Dhaka" was read as "Dnaka"). A CSV encoding was guessed wrongly at first (cp775), which broke "Café Müller", and I fixed it by limiting the choices to UTF-8 and cp1252. In the OCR experiment, the page segmentation mode mattered most (psm 6 was best), and preprocessing changed very little on my clean test files.

Limits: all my test files are synthetic, so real scans will be harder. Encoding detection is a guess and only covers common Western encodings. Next, in Phase 2, I use this text as the input for AI extraction.
## CLI checks on the fixtures 

I ran each fixture through the CLI to see the pipeline work end to end:
dcrun python -m app.pipeline.cli tests/fixtures/<file>
The CLI shows the file type, page count, time, the method used per page and the first 400 characters.

### 1. Digital PDF (invoice_digital.pdf)
- Detected as PDF, 1 page, read from the text layer (no OCR), 556 characters, 19 ms.
- The text was complete and clean, and the columns were kept.
- This is the fast path: if a PDF already has text, I should not OCR it.

### 2. Scanned PDF (invoice_scanned.pdf)
- Detected as PDF, 1 page, read with OCR, confidence 95.1, 289 characters, 1613 ms.
- Same invoice, but about 85 times slower than the text layer.
- OCR made one mistake: "Dhaka" became "Dnaka". Everything else, including the amounts and totals, was correct.
- Lesson: OCR is good but not perfect. Confidence 95 does not mean 100% correct, so later phases must check the values.

### 3. Multi-page TIFF (invoice_multipage.tiff)
- Detected as an image (image/tiff), 2 pages, OCR confidence 94.5 and 95.4, 1045 ms in total.
- Each frame of the TIFF became its own page, as intended.

### 4. Excel (sample.xlsx)
- Detected as xlsx, 2 sheets (Invoices, LineItems), method "table", 114 ms.
- Accents (Café Müller) were correct. Each sheet became one page with its sheet name kept.

### 5. Latin-1 CSV with semicolons (sample_latin1_semicolon.csv)
- The semicolon delimiter was detected correctly, 88 ms.
- Problem: the encoding was guessed as cp775, so "Café Müller" came out as "Cafķ M³ller". The file is really cp1252.
- Cause: charset-normalizer guesses from the bytes, and on a small file with only a few accented characters it can guess wrong.
- Fix: limit the candidates with cp_isolation=['utf_8', 'cp1252']. Result after the fix: "Café Müller" came out perfect just as written in the csv. 
- Trade-off: this only supports UTF-8 and Windows Western encodings. A CSV in another encoding would be decoded wrongly, so the warning "Detected encoding: ..." stays visible.

### What I learned
- The CLI made problems visible that the code alone did not show (the wrong encoding).
- The parser records the method and OCR confidence for every page, so the pipeline can be honest about uncertainty.
- Limits: all fixtures are synthetic and clean. Real scans will be worse.
### ocr_experiment results
What worked well: The OCR experiment gave clear results. Changing the page segmentation mode mattered more than anything else. With psm 3 about 15% of the characters were wrong on every image, but with psm 4 and psm 6 the error rate was almost zero (0.000 on most runs). That means the default of psm 6 in my code is a measured choice and not a guess. The text quality was also good on the low-resolution and skewed images, and each OCR run took only 0.2 to 0.7 seconds, which is fast enough for a normal invoice.

What I am not sure about: Preprocessing made almost no difference on these files. The changes were about 0.003, which is roughly one character, so I count that as noise. On the low-res image it was even slightly worse, and it added about 0.2 seconds on the skewed one. I also saw that the confidence score does not match accuracy: some runs had confidence 94 to 95 while 15% of the text was wrong, so I should not trust confidence alone. The biggest drawback is that all my test files are synthetic, clean and use one invoice layout, so real scans and phone photos will probably do worse. I only tested 3 images, so I cannot say the results hold in general. I keep preprocessing on for real photos, but I still need to test it on real documents.


## Phase 2 summary: gemini 3.5 flash lite api integration and testing (24 Nov 2026)

What I built and how the integration works. In Phase 2 I turned the plain text from Phase 1 into checked invoice data. I wrote one entry point, extract_invoice(), which takes the document text and sends it to Google's Gemini API (gemini-3.5-flash-lite, free tier) through a small client class called GeminiClient. The prompt is stored in its own versioned file (extract_invoice_v1.md), and the answer must come back as JSON in a fixed schema. For every field the model returns the value as printed, an exact quote from the document, and a confidence score. My code then checks each value: the quote must really appear in the document, and the value must be inside the quote. If not, the value is dropped and a warning is added. Amounts become Decimal, dates become ISO dates and currencies become ISO codes, so a missing field stays null instead of being invented. The API key lives only in .env, and only llm.py knows about Gemini, so the provider can be changed later by replacing one class. I created these files: schemas/invoice.py, extraction/errors.py, normalise.py, evidence.py, llm.py, extract.py, the prompt file, two test files, and three scripts (try_extract.py, make_dataset.py, eval_extraction.py). I also generated a labeled dataset of 30 invoices, each as a PDF, a damaged scan and a JSON label, which makes 90 files.

Tests, checks and results. The unit tests use a fake LLM client, so they run without internet or a key. They check normalising of amounts, dates and currencies, and the "no inventing" rules: missing fields stay empty, invented values and invented line items are dropped, and a real quote with the wrong value is rejected . Then I ran the real client on the two Phase 1 fixtures. Both gave correct values, and the currency was left empty because the invoice prints none. Finally I ran the full evaluation on all 60 documents. 59 were extracted and 1 failed, so the success rate is 98.3%. Invoice number, date, customer, subtotal, tax and total were 100% correct. Supplier name was 94.9% and currency 98.3%. All six planted edge cases (missing tax, wrong total, no currency, no customer, duplicate number, European numbers) were handled correctly on both PDF and scan. Split by type, the PDFs were 100% correct and the scans were 90% for supplier name and 96.7% for currency. A single call took about 2 to 2.6 seconds. The average of 20.9 seconds per document in the full run is higher because it includes OCR, a 5-second pause between calls and the retry waits. The full run used 76,226 tokens and about 75 of my 500 free daily requests, so it cost nothing.

Problems I faced and how I fixed them. First, I could not pay for the Anthropic API, so I switched to Gemini's free tier. I rewrote the client and added a 5-second pause between calls and a retry loop to stay under the free limit of 15 requests a minute. Second, I put ExtractionError in the wrong folder (pipeline/errors.py); the later files import it from extraction/errors.py, so I moved it there. Third, VS Code showed a strikethrough on typing.Callable, which is only a deprecation hint, and I changed the import to collections.abc. Fourth, during the evaluation one document (inv_002.pdf) failed with a 503 "high demand" error from Google. It failed after three retries, so it was a temporary capacity problem on their side, not a bug in my code, and in Phase 4 such a job will be marked failed and can be reprocessed. Fifth, four fields were wrong, all on scans: the supplier name on three invoices and the currency on one hard scan.  The limits of these numbers are that the invoices are synthetic, have one layout and have labels generated by code, so real invoices will probably score lower.

## Phase 2 — Extraction accuracy (evaluation run, 24 Nov 2026)

Setup: model `gemini-3.5-flash-lite` (free tier), prompt `extract_invoice_v1`,
dataset `backend/eval_data` (30 synthetic invoices, each as a digital PDF and a damaged scan = 60 documents).
Command: `dcrun python -m scripts.eval_extraction --limit 0`

### Document results

| Metric | Result |
|---|---|
| Documents attempted | 60 |
| Extracted successfully | 59 (98.3%) |
| Failed | 1 (1.7%) — `inv_002.pdf`: Gemini returned 503 "high demand" after 3 retries |
| Total tokens | 76,226 (about 1,290 per document) |
| Cost | 0 (free tier) |
| Average time per document | 20.9 s (includes OCR, the 5 s pause between calls and retry waits) |
| Time of one LLM call | about 2.0–2.6 s (measured with `try_extract`) |

### Field accuracy

| Field | All (59 docs) | PDFs (29 docs) | Scans (30 docs) |
|---|---|---|---|
| invoice_number | 100.0% | 100.0% | 100.0% |
| invoice_date | 100.0% | 100.0% | 100.0% |
| supplier_name | 94.9% | 100.0% | 90.0% (27/30) |
| customer_name | 100.0% | 100.0% | 100.0% |
| subtotal | 100.0% | 100.0% | 100.0% |
| tax | 100.0% | 100.0% | 100.0% |
| total | 100.0% | 100.0% | 100.0% |
| currency | 98.3% | 100.0% | 96.7% (29/30) |

A field counts as correct when it matches the label; a `null` counts as correct only when the label is also `null`.

### Planted edge cases

| Invoice | Edge case | PDF | Scan |
|---|---|---|---|
| inv_005 | missing tax (must stay null) | correct | correct |
| inv_009 | wrong total (must be reported as printed) | correct | correct |
| inv_013 | no currency (must stay null) | correct | correct |
| inv_017 | no customer (must stay null) | correct | correct |
| inv_021 | duplicate invoice number (same as inv_003) | correct | correct |
| inv_025 | European number format (1.234,56) | correct | correct |

### Errors found

| Document | Wrong field |
|---|---|
| inv_004_scan.jpg | supplier_name |
| inv_006_scan.jpg | supplier_name |
| inv_019_scan.jpg | supplier_name |
| inv_028_scan.jpg (hard scan) | currency |

### Conclusion

All four errors are on scans, and every digital PDF was 100% correct, so the remaining errors come from OCR quality, not from the prompt or the code. The system never invented a value: all three "must stay null" cases stayed null on both PDF and scan. The one failure was a temporary capacity error on Google's side, handled by retries and reported as a typed `ExtractionError`. Limits: the invoices are synthetic, use one layout and have labels generated by code, so real invoices will probably score lower.
## Phase 3: validation (25 Nov 2026)

What I built: plain Python rules (no AI) that check the extracted invoice. They check missing fields, subtotal + tax + adjustments = total, line amount = quantity x unit price, line items add up, impossible numbers (zero or negative totals), impossible dates (future, more than 5 years old), fake currency codes (ISO 4217 list, 181 codes), bare dollar signs, and duplicates (same supplier and number, same number from another supplier, renumbered or prefix-dropped, same supplier + date + total). Each invoice gets needs_review with a list of reasons. Rules flag a document for a person; they never change a value. All money uses Decimal with a 0.01 tolerance.

Why: the model copies what is printed, the code decides if it makes sense. If the model "fixed" a wrong total, the evidence of the supplier's mistake would be lost.

| Check | How | Result |
| --- | --- | --- |
| Old tests after Phase 2 changes | pytest | 61 passed |
| Currency list | python check | 181 codes, BDT accepted, XYZ rejected |
| Tests after rules and adjustment tests | pytest | 151 passed |
| 30 labelled invoices, no AI | validate_eval | exactly 5 flagged: inv_005 tax_missing, inv_009 total_mismatch (1094.02 vs 1084.02), inv_013 currency_missing, inv_017 customer_name_missing, inv_021 duplicate_number (same number as inv_003). The other 25 are ok, no false alarms |
| Phase 2 re-check with prompt v2, 6 PDFs | eval_extraction, try_extract | 6 of 6 all fields correct (3 needed a retry because of Gemini 503) |
| Planted cases with real Gemini | try_validate | inv_003 clean, inv_005 tax_missing, inv_021 duplicate_number of inv_003. inv_009: see docs/phase3_inv009.txt |
| 21 corner cases, real Gemini, prompt v2 | try_validate | 16 of 18 extracted matched. e18 was a real DIFF, e16 DIFF only because its partner e02 hit a 503 |
| 21 corner cases, real Gemini, prompt v3 | try_validate | 19 of 21 MATCH, 0 DIFF. e04 and e08: see docs/phase3_real_run_part3.txt |
| 3 own made-up documents (new layouts, discount and shipping rows, EUR scan) | try_validate | see docs/phase3_my_docs.txt |

Findings:
1. Prompt v2 broke on invoice e18: rows like "Delivery fee" and "Loyalty discount" sat INSIDE the items table, but v2 said adjustments are rows between subtotal and total, so Gemini put them there. The rules caught it (total_mismatch and line_items_sum_mismatch). I fixed the prompt (v3: position decides, rows above the subtotal line are line items), not the rules. Old prompts are never edited, v1 and v2 stay as they were.
2. Gemini free tier returns 503 "high demand" at random. In one run 6 of 21 files failed, a different set each time, and the run took about 22 minutes because each failed file waits 15 + 30 + 60 seconds. It is not a code bug. In production this becomes a background job with retries and a reprocess endpoint (Phase 4).
3. Known gaps: supplier names damaged by OCR can hide a fuzzy duplicate, several invoices in one PDF, two currencies on one invoice, percent-only discounts with no printed amount, handwriting. Cross-verification (PDF-PDF, PDF-Excel) is not built.

### Final test run
............................                                             [100%]

14 of 21 need review: e05_tax_included, e06_no_subtotal, e07_credit_note, e08_zero_total, e09_future_date, e10_old_date, e11_ambiguous_date, e12_fake_currency, e13_dollar_only, e14_exact_duplicate, e15_supplier_spelling, e16_same_date_and_total, e17_number_drift, e20_wrong_line_amount
