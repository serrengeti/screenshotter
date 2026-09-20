"""
Extract text from all images in a folder using EasyOCR (strong accuracy on printed text).

Install:  python -m pip install -r requirements-ocr.txt
First run downloads model files (one-time, needs network).

CPU: Full-resolution screenshots are very slow; defaults resize the long edge and use a
smaller detection canvas. See --max-side and --canvas-size.
"""

from __future__ import annotations

import os

# Windows: PyTorch/EasyOCR and MKL can each link Intel OpenMP (libiomp5md.dll); without this,
# the process can abort with OMP: Error #15. Must run before importing torch (via easyocr).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import argparse
import sys
import warnings
from pathlib import Path

try:
    import easyocr
except ModuleNotFoundError as e:
    if e.name != "easyocr":
        raise
    print(
        "easyocr is not installed.\n\n"
        "Run:\n"
        "  python -m pip install -r requirements-ocr.txt\n\n"
        "Or:  python -m pip install easyocr",
        file=sys.stderr,
    )
    sys.exit(1)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _load_image_array(path: Path, max_side: int | None):
    """RGB uint8 array; optionally downscale so CPU OCR finishes in reasonable time."""
    import numpy as np
    from PIL import Image

    im = Image.open(path).convert("RGB")
    if max_side is not None and max(im.size) > max_side:
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:  # Pillow < 9
            resample = Image.LANCZOS
        im.thumbnail((max_side, max_side), resample)
    return np.asarray(im)


def collect_images(folder: Path, recursive: bool) -> list[Path]:
    if recursive:
        paths = [p for p in folder.rglob("*") if p.is_file()]
    else:
        paths = [p for p in folder.iterdir() if p.is_file()]
    images = [p for p in paths if p.suffix.lower() in IMAGE_EXTENSIONS]
    return sorted(images, key=lambda p: p.name.lower())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR all images in a folder into one .txt file (EasyOCR).",
    )
    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing images (PNG, JPG, etc.)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        required=True,
        help="Folder where the .txt file will be written (created if missing)",
    )
    parser.add_argument(
        "--filename",
        default="extracted_text.txt",
        help="Name of the output text file (default: extracted_text.txt)",
    )
    parser.add_argument(
        "--lang",
        nargs="+",
        default=["en"],
        metavar="CODE",
        help="EasyOCR language codes (default: en). Example: --lang en ar",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Include images in subfolders",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use GPU if CUDA is available (requires PyTorch with CUDA)",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=1800,
        metavar="PX",
        help="Resize so longest edge is at most this many pixels before OCR "
        "(default: 1800; use 0 to disable resize — much slower on CPU)",
    )
    parser.add_argument(
        "--canvas-size",
        type=int,
        default=1280,
        metavar="PX",
        help="EasyOCR detection canvas size (default: 1280; use 2560 for max quality, slower)",
    )
    args = parser.parse_args()

    input_folder = args.input_folder.resolve()
    if not input_folder.is_dir():
        raise SystemExit(f"Not a folder: {input_folder}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_name = args.filename.strip() or "extracted_text.txt"
    if not out_name.lower().endswith(".txt"):
        out_name += ".txt"
    out_path = output_dir / out_name

    images = collect_images(input_folder, args.recursive)
    if not images:
        raise SystemExit(
            f"No images found in {input_folder} "
            f"(supported: {', '.join(sorted(IMAGE_EXTENSIONS))})"
        )

    # PyTorch DataLoader warns about pin_memory when no CUDA — harmless noise.
    warnings.filterwarnings("ignore", message=".*pin_memory.*", category=UserWarning)

    use_gpu = False
    if args.gpu:
        try:
            import torch

            use_gpu = bool(torch.cuda.is_available())
        except ImportError:
            use_gpu = False

    max_side = args.max_side if args.max_side > 0 else None
    if max_side is None:
        print(
            "No resize (--max-side 0): each page can take many minutes on CPU. "
            "Press Ctrl+C to stop; partial output will be saved.",
            file=sys.stderr,
        )

    reader = easyocr.Reader(args.lang, gpu=use_gpu, verbose=False)

    n = len(images)
    chunks: list[str] = []

    def write_out() -> None:
        out_path.write_text("".join(chunks), encoding="utf-8")

    try:
        for i, img_path in enumerate(images, start=1):
            rel = img_path.name if not args.recursive else str(
                img_path.relative_to(input_folder)
            )
            print(f"[{i}/{n}] OCR: {rel}", flush=True)
            chunks.append(f"{'=' * 72}\n{rel}\n{'=' * 72}\n")
            img_array = _load_image_array(img_path, max_side)
            results = reader.readtext(
                img_array,
                detail=0,
                paragraph=True,
                canvas_size=args.canvas_size,
            )
            if isinstance(results, str):
                text = results
            else:
                text = "\n".join(results) if results else ""
            chunks.append(text.rstrip() + "\n\n")
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).", file=sys.stderr)
        if chunks:
            write_out()
            print(f"Partial text saved to: {out_path}", file=sys.stderr)
        raise SystemExit(130) from None

    write_out()
    print(f"Done. Wrote {n} image(s) to {out_path}")


if __name__ == "__main__":
    main()
