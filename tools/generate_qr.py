"""
빈에 부착할 QR 코드 PNG 생성.

사용:
    python tools/generate_qr.py                    # 기본 (BIN-01~04 + DEPOT)
    python tools/generate_qr.py --ids ABC XYZ      # 임의 ID 지정
    python tools/generate_qr.py --size 400         # 픽셀 사이즈 (기본 300)
    python tools/generate_qr.py --out qrs/         # 출력 폴더

설치:
    pip install qrcode[pil]
"""
import argparse
import os
import sys

DEFAULT_IDS = ["BIN-01", "BIN-02", "BIN-03", "BIN-04", "DEPOT"]


def generate(ids: list[str], size_px: int, out_dir: str, label: bool = True):
    try:
        import qrcode
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("ERROR: pip install 'qrcode[pil]'", file=sys.stderr)
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    for code_id in ids:
        qr = qrcode.QRCode(
            version=1, error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10, border=4,
        )
        qr.add_data(code_id)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((size_px, size_px), Image.NEAREST)

        if label:
            label_h = 40
            canvas = Image.new("RGB", (size_px, size_px + label_h), "white")
            canvas.paste(img, (0, 0))
            draw = ImageDraw.Draw(canvas)
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
            except Exception:
                font = ImageFont.load_default()
            tw = draw.textlength(code_id, font=font)
            draw.text(((size_px - tw) / 2, size_px + 4), code_id, fill="black", font=font)
            img = canvas

        path = os.path.join(out_dir, f"{code_id}.png")
        img.save(path)
        print(f"✓ {path}  ({size_px}x{size_px})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", default=DEFAULT_IDS)
    ap.add_argument("--size", type=int, default=300)
    ap.add_argument("--out", default="qrs")
    ap.add_argument("--no-label", action="store_true")
    args = ap.parse_args()

    generate(args.ids, args.size, args.out, label=not args.no_label)
    print(f"\n총 {len(args.ids)}개 생성 → {args.out}/")
    print("출력해서 빈/수거함에 부착하세요. 권장: A4에 인쇄, 코팅 후 부착.")


if __name__ == "__main__":
    main()
