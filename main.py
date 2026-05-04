"""
RidePro - Hệ thống đặt xe thông minh
Entry point: chạy `python main.py` để khởi động server Flask.

Mặc định mở tại http://127.0.0.1:5000

Có thể đổi PORT/HOST qua biến môi trường:
  PORT=5000  HOST=0.0.0.0  python main.py
"""
import os

from backend import setup_backend


app = setup_backend()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    print("=" * 60)
    print("  RIDEPRO - HỆ THỐNG ĐẶT XE THÔNG MINH")
    print(f"  Server đang chạy tại: http://{host}:{port}")
    print("  Nhấn CTRL+C để dừng server.")
    print("=" * 60)
    app.run(host=host, port=port, debug=False, threaded=True)
