"""QR code generation for bin identification."""
import io
import qrcode


def generate_qr_image(data: str, size: int = 10) -> bytes:
    """Generate QR code as PNG bytes.

    Args:
        data: String data to encode (typically JSON)
        size: Box size for QR modules

    Returns:
        PNG image bytes
    """
    qr = qrcode.QRCode(version=1, box_size=size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
