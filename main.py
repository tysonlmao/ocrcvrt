import os
import sys
import argparse
from pathlib import Path
from typing import Iterable, Tuple

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

def load_working_dir_from_env() -> Path:
    """Load WORKING_DIR from .env or environment and return as Path.

    Raises a clear error if not configured or path does not exist.
    """
    # Load from .env if python-dotenv is available
    if load_dotenv is not None:
        load_dotenv(override=False)

    working_dir = os.getenv("WORKING_DIR", "").strip()
    if not working_dir:
        raise SystemExit(
            "WORKING_DIR is not set. Create a .env file with WORKING_DIR=/absolute/path or export it in your shell."
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


def derive_output_path(src: Path, out_dir: Path | None, target_ext: str) -> Path:
    """Compute output path for converted image.

    - If out_dir is provided, mirror the relative structure under out_dir.
    - Otherwise, write next to source with new extension.
    - Avoid overwriting by appending a numeric suffix if needed.
    """
    target_ext = target_ext if target_ext.startswith(".") else f".{target_ext}"
    if out_dir:
        rel = src.relative_to(src.anchor if src.is_absolute() else src.parents[len(src.parents) - 1])
        # Safer: compute relative to the common root (working dir) in caller; here we just keep filename
        rel = src.name
        candidate = Path(out_dir) / Path(rel).with_suffix(target_ext)
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


def convert_to_ocr_friendly(src: Path, output_format: str = "PNG", dpi: int = 300) -> Tuple[Path, bool]:
    """Convert an image to an OCR-friendly format at given DPI.

    Returns (output_path, changed)
    - If already OCR-friendly, returns (src, False)
    - Else writes PNG next to it (or TIFF if requested) and returns (new_path, True)
    """
    if is_ocr_friendly(src):
        return src, False

    target_ext = ".png" if output_format.upper() == "PNG" else ".tiff"
    output_path = derive_output_path(src, out_dir=None, target_ext=target_ext)

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

    args = parser.parse_args(argv)
    working_dir = load_working_dir_from_env()

    if args.verbose:
        print(f"WORKING_DIR={working_dir}")
        total_files = sum(1 for p in working_dir.rglob("*") if p.is_file())
        pre_candidates = list(iter_candidate_files(working_dir))
        print(f"Found {total_files} files; {len(pre_candidates)} candidate image files")
        candidates: Iterable[Path] = pre_candidates
        if not pre_candidates:
            print(
                "No candidate images found. Supported input extensions: "
                + ", ".join(sorted(RASTER_IMAGE_EXTENSIONS))
            )
    else:
        candidates = iter_candidate_files(working_dir)

    total = 0
    converted = 0
    skipped = 0

    for file_path in candidates:
        total += 1
        if is_ocr_friendly(file_path):
            skipped += 1
            print(f"SKIP (already OCR-friendly): {file_path}")
            continue

        if args.dry_run:
            print(f"CONVERT (dry-run): {file_path} -> {args.format}@{args.dpi}DPI")
            continue

        out_path, changed = convert_to_ocr_friendly(file_path, output_format=args.format, dpi=args.dpi)
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

