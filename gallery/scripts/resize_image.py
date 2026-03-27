"""Resize a gallery image for the README thumbnail."""
import argparse
from PIL import Image

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", help="Output image path")
    parser.add_argument("--size", type=int, default=400, help="Max dimension in pixels")
    args = parser.parse_args()

    img = Image.open(args.input)
    img.thumbnail((args.size, args.size), Image.LANCZOS)
    img.save(args.output, quality=80)

if __name__ == "__main__":
    main()
