# ============================================================
# download_fonts.py — Скачивание шрифтов DejaVu для PDF
# ============================================================
# Запустите один раз перед первым использованием PDF-экспорта:
#   python download_fonts.py
# ============================================================

import urllib.request
import os
import sys

FONTS = {
    "fonts/DejaVuSans.ttf": (
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master"
        "/ttf/DejaVuSans.ttf"
    ),
    "fonts/DejaVuSans-Bold.ttf": (
        "https://github.com/dejavu-fonts/dejavu-fonts/raw/master"
        "/ttf/DejaVuSans-Bold.ttf"
    ),
}


def main():
    os.makedirs("fonts", exist_ok=True)
    print("📥 Скачивание шрифтов DejaVu для поддержки кириллицы в PDF...\n")

    for path, url in FONTS.items():
        if os.path.exists(path):
            size = os.path.getsize(path) // 1024
            print(f"  ✅ {path} уже существует ({size} KB)")
            continue

        try:
            print(f"  ⏳ Скачиваю {path}...")
            urllib.request.urlretrieve(url, path)
            size = os.path.getsize(path) // 1024
            print(f"     → Готово ({size} KB)")
        except Exception as e:
            print(f"  ❌ Ошибка при скачивании {path}: {e}")
            sys.exit(1)

    print("\n✅ Все шрифты готовы к использованию!")


if __name__ == "__main__":
    main()
