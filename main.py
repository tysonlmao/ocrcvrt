import os
import sys
import csv
import argparse
from pathlib import Path
from typing import Iterable, Tuple, List, Optional

try:
    from PIL import Image, ImageOps
except Exception as exc:  # pragma: no cover
    print("Pillow is required. Install with: pip install Pillow python-dotenv", file=sys.stderr)
    raise

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # fallback if not installed; env must be present


OCR_FRIENDLY_EXTENSIONS = {".png", ".tif", ".tiff", ".pbm", ".pgm", ".ppm"}
RASTER_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif"}

def load_directories_from_csv(csv_path: Path) -> List[Path]:
    """Load a list of directories to scan from a CSV file.

    Accepts either a header 'path' or plain rows where the first column is a directory path.
    Ignores empty lines and lines starting with '#'.
    """
    directories: List[Path] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header_seen = False
        path_column_index: Optional[int] = None
        for row in reader:
            if not row:
                continue
            # join to support commas inside quotes handled by csv module; strip whitespace
            first_cell = (row[0] or "").strip()
            if first_cell.startswith("#"):
                continue
            if not header_seen:
                header_seen = True
                lowered = [c.strip().lower() for c in row]
                if "path" in lowered:
                    path_column_index = lowered.index("path")
                    # go to next row for actual data
                    continue
                else:
                    path_column_index = 0
                    # fall through to treat this row as data
            # data row
            idx = 0 if path_column_index is None else path_column_index
            if idx >= len(row):
                continue
            raw_path = (row[idx] or "").strip()
            if not raw_path:
                continue
            p = Path(raw_path).expanduser().resolve()
            if not p.exists() or not p.is_dir():
                print(f"WARN: skipping non-existent directory from CSV: {raw_path}", file=sys.stderr)
                continue
            directories.append(p)

    if not directories:
        raise SystemExit(f"No valid directories found in CSV: {csv_path}")
    return directories


def load_single_working_dir_from_env() -> Path:
    """Fallback: Load WORKING_DIR from environment/.env for single-directory scans."""
    if load_dotenv is not None:
        load_dotenv(override=False)
    working_dir = os.getenv("WORKING_DIR", "").strip()
    if not working_dir:
        raise SystemExit(
            "Either provide --csv PATH to a CSV of folders, or set WORKING_DIR=/absolute/path."
        )
    path = Path(working_dir).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise SystemExit(f"WORKING_DIR does not exist or is not a directory: {path}")
    return path


def is_ocr_friendly(file_path: Path) -> bool:
    """Determine if the file is already in an OCR-friendly raster format.

    For this script, we consider PNG and TIFF (and PBM/PGM/PPM) as OCR-ready containers.
    This does not guarantee good OCR quality; it's just a container/format check.
    """
    return file_path.suffix.lower() in OCR_FRIENDLY_EXTENSIONS


def iter_candidate_files(root: Path) -> Iterable[Path]:
    """Yield files under root that are images we may convert for OCR friendliness."""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in RASTER_IMAGE_EXTENSIONS:
            yield path


def derive_output_path(src: Path, root_dir: Optional[Path], out_dir: Optional[Path], target_ext: str) -> Path:
    """Compute output path for converted image.

    - If out_dir is provided, mirror the relative structure under out_dir.
    - Otherwise, write next to source with new extension.
    - Avoid overwriting by appending a numeric suffix if needed.
    """
    target_ext = target_ext if target_ext.startswith(".") else f".{target_ext}"
    if out_dir:
        # Mirror structure relative to root_dir when provided; else fall back to just the filename
        if root_dir and src.is_absolute():
            try:
                rel = src.relative_to(root_dir)
            except ValueError:
                rel = Path(src.name)
        else:
            rel = Path(src.name)
        candidate = Path(out_dir) / rel.with_suffix(target_ext)
    else:
        candidate = src.with_suffix(target_ext)

    if candidate == src:
        # Source already has desired extension; add suffix
        candidate = candidate.with_name(candidate.stem + "_ocr" + candidate.suffix)

    idx = 1
    final_path = candidate
    while final_path.exists():
        final_path = candidate.with_name(f"{candidate.stem}_{idx}{candidate.suffix}")
        idx += 1
    return final_path


def convert_to_ocr_friendly(
    src: Path,
    output_format: str = "PNG",
    dpi: int = 300,
    *,
    root_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[Path, bool]:
    """Convert an image to an OCR-friendly format at given DPI.

    Returns (output_path, changed)
    - If already OCR-friendly, returns (src, False)
    - Else writes PNG/TIFF either next to it or under output_dir and returns (new_path, True)
    """
    if is_ocr_friendly(src):
        return src, False

    target_ext = ".png" if output_format.upper() == "PNG" else ".tiff"
    output_path = derive_output_path(src, root_dir=root_dir, out_dir=output_dir, target_ext=target_ext)

    with Image.open(src) as im:
        # Ensure single mode that preserves information for OCR
        # Convert paletted or CMYK to RGB; keep alpha if present
        if im.mode in {"P", "CMYK"}:
            im = im.convert("RGB")
        # Some formats may be lazy; ensure it's loaded before operations
        im.load()

        # Auto-orient based on EXIF and remove metadata to reduce surprises
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass

        save_params = {"dpi": (dpi, dpi)}
        if output_format.upper() == "PNG":
            save_params["optimize"] = True
        else:  # TIFF
            save_params["compression"] = "tiff_deflate"

        # Ensure parent folder exists when writing into an output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(output_path, output_format.upper(), **save_params)

    return output_path, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a directory and ensure images are in OCR-capable formats (PNG/TIFF)."
    )
    parser.add_argument(
        "--format",
        choices=["PNG", "TIFF"],
        default="PNG",
        help="Target OCR-friendly output format",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Target DPI for saved images (typical OCR uses 300).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list actions without writing files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra information about scanning and candidates.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Path to CSV file listing folders to scan (column 'path' or first column).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path.home() / "ocr_output"),
        help="Directory to write converted files into (default: ~/ocr_output).",
    )

    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()

    # Resolve list of root directories to scan
    root_dirs: List[Path]
    if args.csv:
        csv_path = Path(args.csv).expanduser().resolve()
        if not csv_path.exists():
            raise SystemExit(f"CSV not found: {csv_path}")
        root_dirs = load_directories_from_csv(csv_path)
    else:
        # Fallback to single-directory env variable for backward compatibility
        root_dirs = [load_single_working_dir_from_env()]

    if args.verbose:
        print(f"OUTPUT_DIR={output_dir}")
        print(f"Roots to scan: {len(root_dirs)}")

    total = 0
    converted = 0
    skipped = 0

    for root_dir in root_dirs:
        if args.verbose:
            print(f"Scanning: {root_dir}")
        # Verbose stats per-root if requested
        if args.verbose:
            total_files = sum(1 for p in root_dir.rglob("*") if p.is_file())
            pre_candidates = list(iter_candidate_files(root_dir))
            print(f"  Files: {total_files}; candidate images: {len(pre_candidates)}")
            candidates: Iterable[Path] = pre_candidates
            if not pre_candidates:
                print(
                    "  No candidate images found. Supported input extensions: "
                    + ", ".join(sorted(RASTER_IMAGE_EXTENSIONS))
                )
        else:
            candidates = iter_candidate_files(root_dir)

        for file_path in candidates:
            total += 1
            if is_ocr_friendly(file_path):
                skipped += 1
                print(f"SKIP (already OCR-friendly): {file_path}")
                continue

            if args.dry_run:
                print(
                    f"CONVERT (dry-run): {file_path} -> {args.format}@{args.dpi}DPI into {output_dir}"
                )
                continue

            out_path, changed = convert_to_ocr_friendly(
                file_path,
                output_format=args.format,
                dpi=args.dpi,
                root_dir=root_dir,
                output_dir=output_dir,
            )
            if changed:
                converted += 1
                print(f"CONVERTED: {file_path} -> {out_path}")
            else:
                skipped += 1
                print(f"SKIP: {file_path}")

    print(
        f"Done. scanned={total}, converted={converted}, already_ok={skipped}"  # summary
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

