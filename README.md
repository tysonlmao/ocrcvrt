### OCR Converter

Convert images in a folder to an OCR‑friendly format (PNG or TIFF) at 300 DPI.

This helps downstream OCR tools read your images more reliably.

### What it does

- Scans your chosen folder (and subfolders)
- Skips images already in an OCR‑friendly format (PNG/TIFF)
- Converts other raster images (e.g., JPG, BMP, WEBP, HEIC/HEIF\*) to PNG (default) or TIFF
- Saves the converted file next to the original without overwriting

Note: HEIC/HEIF support depends on your system and Pillow build.

### Requirements

- Python 3.10 or newer
- Dependencies from `requirements.txt`

### 1) Install dependencies

Open Terminal in this folder and run:

```bash
pip install -r requirements.txt
```

### 2) Tell the script which folder to scan

You can set the folder in either of two ways.

Option A — Create a `.env` file in this folder with:

```bash
WORKING_DIR=/absolute/path/to/your/images
```

Option B — Set it just for your current Terminal session:

```bash
export WORKING_DIR="/absolute/path/to/your/images"
```

Tip: On macOS, you can drag a folder into the Terminal window to paste its absolute path.

### 3) Try a dry run (no files are written)

```bash
python main.py --verbose --dry-run
```

You’ll see the resolved folder and how many images were found.

### 4) Convert images

- Convert to PNG at 300 DPI (default):

```bash
python main.py
```

### Supported input types

jpg, jpeg, png, tif, tiff, bmp, webp, heic, heif

### What you’ll see

- "SKIP (already OCR-friendly)" for PNG/TIFF files
- "CONVERTED" for files that were converted (a new file is created)
- A summary line when finished, e.g. `Done. scanned=42, converted=10, already_ok=32`

### Troubleshooting

- Error: WORKING_DIR is not set

  - Create a `.env` file (see step 2) or run `export WORKING_DIR="/path"` in Terminal.

- No images found (0 candidates)

  - Check the path in `WORKING_DIR` is correct
  - Ensure the folder actually contains supported image files

- HEIC/HEIF won’t open
  - Some Pillow installs don’t include HEIC/HEIF support by default. Consider converting those files to JPG/PNG first using Preview (macOS) or another tool, then run this script.

### Uninstalling

This script doesn’t install anything system‑wide. To remove it, just delete the folder. Converted images created by the script will remain where they were saved.
