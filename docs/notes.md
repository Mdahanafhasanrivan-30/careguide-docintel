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

