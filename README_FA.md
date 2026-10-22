# افزونهٔ OpenVPN برای SpiderPanel (نسخهٔ آزمایشی)

این بسته یک ادغام مستقل و نوشته‌شده برای بک‌اند Python/FastAPI پروژهٔ SpiderPanel است. کد OpenVPN را از `vpn-ui` کپی نمی‌کند؛ چون `vpn-ui` یک پروژهٔ Go است و SpiderPanel با Python/FastAPI نوشته شده. کپی مستقیم فایل‌های Go داخل SpiderPanel کار نمی‌کند و ممکن است الزامات مجوز GPL-3.0 مخزن `vpn-ui` را هم ایجاد کند.

> **وضعیت:** نسخهٔ اولیه برای آزمایش روی VPS جداست؛ ممیزی امنیتی مستقل یا آزمایش اتصال واقعی روی سرور در این محیط انجام نشده است. قبل از سرور اصلی، روی VPS آزمایشی تست کن.

## قابلیت‌های نسخهٔ اولیه

- پنل وب فارسی/راست‌چین در مسیر `/openvpn` با احراز هویت همان نشست SpiderPanel.
- ساخت کاربر با گواهی و کلید اختصاصی Easy-RSA.
- دانلود پروفایل `.ovpn` با CA، گواهی، کلید کاربر و `tls-crypt` به‌صورت inline.
- لغو گواهی، ساخت CRL و راه‌اندازی مجدد OpenVPN برای اعمال CRL.
- نام کاربری محدود و فراخوانی کنترل‌گر با `subprocess` و آرگومان‌های ثابت، بدون اجرای shell از دادهٔ کاربر.
- SQLite با فایل دسترسی محدود برای ثبت وضعیت کاربران.
- کنترل CSRF ساده با تطبیق Origin/Referer با میزبان پنل و هدرهای `no-store` برای فایل کانفیگ.

**فعلاً پیاده‌سازی نشده:** محدودیت حجم OpenVPN، آمار لحظه‌ای ترافیک، تاریخ انقضای مدیریتی در پنل، تعداد اتصال هم‌زمان، نماینده/زیرمجموعه و نمایش اتصال آنلاین. تاریخ انقضای گواهی با مقدار پیش‌فرض Easy-RSA در زمان نصب تعیین می‌شود و در UI قابل مدیریت نیست. در هنگام لغو گواهی، سرویس راه‌اندازی مجدد می‌شود و همهٔ اتصال‌های فعال OpenVPN قطع خواهند شد.

## ساختار فایل‌ها

- `openvpn_addon.py` — API و مسیر صفحه برای FastAPI.
- `openvpn.html` — رابط کاربری فارسی.
- `spider-openvpnctl` — کنترل‌گر محدود سمت root؛ مسیرها و دستورات درون آن ثابت هستند.
- `setup_openvpn_server.sh` — نصب اولیهٔ OpenVPN/Easy-RSA فقط روی Ubuntu/Debian، با تأیید صریح و توقف در صورت تشخیص پیکربندی/PKI موجود.
- `apply_spiderpanel_patch.py` — اسکریپت الحاق router به `main.py` و افزودن لینک منو با فایل پشتیبان.

## قبل از شروع

1. از VPS آزمایشی استفاده کن. نصب‌کننده یک CA جدید ایجاد می‌کند و تنظیمات forwarding/NAT اضافه می‌کند.
2. اگر OpenVPN از قبل نصب یا استفاده می‌شود، **`setup_openvpn_server.sh` را اجرا نکن**. اسکریپت در صورت یافتن `server.conf` یا PKI موجود متوقف می‌شود، اما وضعیت‌های سفارشی همهٔ سرورها را نمی‌تواند تشخیص دهد.
3. از `/opt/SpiderPanel/main.py`، `static/index.html` و داده‌های پنل بکاپ بگیر.
4. قبل از دانلود کانفیگ به مشتری، HTTPS پنل را فعال کن و پورت پنل را از اینترنت عمومی محدود کن. فایل `.ovpn` شامل کلید خصوصی کاربر است؛ مثل رمز عبور با آن رفتار کن.

## نصب فایل‌ها

بسته را در محیط خود استخراج کن و پنج فایل آن را کنار `/opt/SpiderPanel/main.py` قرار بده:

```text
/opt/SpiderPanel/
  main.py
  openvpn_addon.py
  openvpn.html
  apply_spiderpanel_patch.py
  setup_openvpn_server.sh
  spider-openvpnctl
  static/index.html
```

در این چیدمان فایل `openvpn.html` عمداً کنار `main.py` است؛ آن را به مسیر دیگری منتقل نکن مگر اینکه مسیر `page_file` در کد تغییر کند.

### ۱) نصب اولیهٔ سرویس OpenVPN (فقط روی سرور خالی)

از پوشه‌ای که فایل‌ها در آن قرار گرفته‌اند:

```bash
cd /opt/SpiderPanel
chmod 750 setup_openvpn_server.sh spider-openvpnctl apply_spiderpanel_patch.py
sudo ./setup_openvpn_server.sh
```

اسکریپت آدرس IP عمومی یا دامنه را می‌پرسد و پیش از تغییر سیستم لازم است دقیقاً `INSTALL` وارد شود. سرویس روی **UDP/1194** نصب می‌شود. اگر پنل فایروال ارائه‌دهندهٔ VPS دارد، UDP/1194 را آنجا هم باز کن. این اسکریپت قواعد قبلی iptables را flush نمی‌کند؛ یک قانون NAT اختصاصی اضافه می‌کند.

فایل CA خصوصی در `/etc/openvpn/easy-rsa/pki/private/ca.key` روی همان سرور نگهداری می‌شود و فقط root باید به آن دسترسی داشته باشد. اگر سرور root-compromise شود، مهاجم ممکن است بتواند گواهی‌های جدید صادر کند؛ به همین دلیل نصب افزونه به معنای امن شدن کامل میزبان نیست.

### ۲) افزودن API و لینک منو

ابتدا فایل‌ها را در مسیر `/opt/SpiderPanel` گذاشته و بکاپ گرفته باش. سپس:

```bash
cd /opt/SpiderPanel
sudo python3 apply_spiderpanel_patch.py --app-dir /opt/SpiderPanel
```

این اسکریپت پیش از تغییر، از هر فایل تغییریافته نسخه‌ای با پسوند `.openvpn-backup-YYYYMMDD-HHMMSS` می‌سازد. اگر ساختار `main.py` متفاوت باشد، از اضافه کردن router خودداری می‌کند. اسکریپت را با `python3` سیستم اجرا کن؛ وابستگی جدیدی نیاز ندارد.

در صورت نیاز به الحاق دستی، این دو خط باید در انتهای `main.py`، پس از تعریف `require_auth` و ساخته شدن `app` قرار گیرند:

```python
from openvpn_addon import build_router as _build_openvpn_router
app.include_router(_build_openvpn_router(require_auth))
```

### ۳) راه‌اندازی مجدد و تست

```bash
sudo systemctl restart spider-panel
sudo systemctl status openvpn-server@server --no-pager
sudo systemctl status spider-panel --no-pager
```

پس از ورود به SpiderPanel، گزینهٔ **OpenVPN** باید در منو دیده شود. مسیر مستقیم صفحه: `/openvpn`.

اگر گزینهٔ منو ظاهر نشد، `/openvpn` را مستقیم باز کن و بررسی کن که `apply_spiderpanel_patch.py` پیام افزودن لینک را داده باشد. به‌روزرسانی SpiderPanel ممکن است تغییر `main.py` یا منو را با نسخهٔ upstream عوض کند؛ تغییرات را بعد از هر به‌روزرسانی با diff بررسی کن و کورکورانه patch را روی نسخهٔ جدید اجرا نکن.

## تنظیمات و مسیرها

اسکریپت نصب، متغیرها را به `/etc/spider-panel.env` اضافه می‌کند (مسیر پیش‌فرض سرویس در نصب‌کنندهٔ SpiderPanel):

- `SPIDER_OPENVPN_PUBLIC_HOST` — آی‌پی یا دامنهٔ عمومی سرور.
- `SPIDER_OPENVPN_PORT=1194` — پورت OpenVPN.
- `SPIDER_OPENVPN_PROTO=udp` — نسخهٔ فعلی فقط UDP.
- `SPIDER_OPENVPN_CTL=/usr/local/sbin/spider-openvpnctl` — مسیر کنترل‌گر ثابت.
- `SPIDER_OPENVPN_USE_SUDO=0` — نصب استاندارد SpiderPanel فعلی با کاربر root اجرا می‌شود.
- `SPIDER_OPENVPN_REQUIRE_HTTPS=1` — دانلود فایل حاوی کلید خصوصی روی HTTP مسدود است؛ reverse proxy باید HTTPS معتبر را فعال کرده و `X-Forwarded-Proto` را درست ارسال کند.
- `SPIDER_OPENVPN_DB=/opt/SpiderPanel/data/openvpn.sqlite3` — دیتابیس افزونه.

اگر سرویس SpiderPanel را تغییر داده‌ای یا مسیر متفاوت است، این مقادیر را با نصب خودت هماهنگ کن. اجرای پنل به‌عنوان root ریسک امنیتی دارد؛ این افزونه آن ریسک کلی را رفع نمی‌کند. در صورت اجرای پنل با کاربر غیر-root، باید فراخوانی helper و مجوزهای فایل‌ها را جداگانه و با دسترسی محدود تنظیم کنی؛ صرفاً `SPIDER_OPENVPN_USE_SUDO=1` را بدون بررسی sudoers فعال نکن.

## بررسی امنیتی/عملیاتی قبل از انتشار

- روی کلاینت آزمایشی اتصال، DNS، IPv4 خروجی و قطع/وصل را آزمایش کن.
- یک کاربر آزمایشی بساز، فایل را در OpenVPN Connect وارد کن، بعد دسترسی‌اش را لغو و اتصال مجدد را امتحان کن.
- لغو گواهی سرویس OpenVPN را restart می‌کند و تمام کاربران متصل را قطع می‌کند؛ زمان مناسب نگهداری را انتخاب کن.
- فایل `.ovpn` حاوی private key است و سرور نیز آن را برای صدور دوباره نگه می‌دارد. دانلودها در پاسخ وب `no-store` دارند، اما مرورگر، اپراتور، بکاپ‌ها و دستگاه مشتری همچنان نقاط حساس‌اند.
- قبل از فروش سرویس، به انقضای CRL، تمدید CRL، بکاپ محرمانهٔ PKI، محدودسازی دسترسی پنل، HTTPS، به‌روزرسانی Easy-RSA/OpenVPN و مانیتورینگ توجه کن.
- تست‌های این بسته، تست استاتیک و syntax check هستند؛ تست نفوذ یا تضمین امنیت محسوب نمی‌شوند.

## بازیابی از تغییر منو/API

فایل‌های `.openvpn-backup-*` را می‌توان برای برگرداندن نسخهٔ قبل استفاده کرد. اگر پنل بالا نیامد:

```bash
sudo journalctl -u spider-panel -n 100 --no-pager
```

برای برگشت سریع، نسخهٔ پشتیبان `main.py` را به‌صورت موقت بازگردان و سرویس را restart کن. این کار به خود سرویس OpenVPN دست نمی‌زند.
