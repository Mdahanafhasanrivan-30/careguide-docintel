# Phase 0 notes (my own words)

1. I have set up the wsl and integrated it ,checked the version,integrated ubuntu and installed docker desktop.
2. I would have used virtual machine but docker desktop is far more valuable because of its speed, device independency and virual host kernel . I can keep a package of all elements of my project.
3. I ran all commands in linux to set up initial backend,api,venv and database and build the docket to up the initial project. checked the testing criterias for security myself and updated readme file.

## Phase 1: CLI checks on the fixtures 

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