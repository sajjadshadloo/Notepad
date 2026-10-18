# ساخت از سورس

بستهٔ ۴.۶.۱ با Python 3.13.12 روی ویندوز ۶۴ بیتی ساخته شده است. برای ساخت نسخهٔ منتشرشده، سورس tag همان نسخه را دریافت کن.

```powershell
pip install -r requirements.txt
python main.py
```

اجرای آزمون‌ها:

```powershell
python -m pytest -q
```

ساخت فایل اجرایی و نصاب؛ مرحلهٔ دوم به Inno Setup نیاز دارد:

```powershell
python -m PyInstaller notepad.spec --noconfirm
ISCC.exe installer.iss
```

کلیدهای سرویس و دادهٔ واقعی کاربر برای ساخت برنامه لازم نیستند. [نسخه و سورس وابستگی‌ها](DEPENDENCY-SOURCES.txt)
