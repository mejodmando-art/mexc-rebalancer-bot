<div dir="rtl" align="right">

# 🤖 MEXC Smart Portfolio — دليل التشغيل الكامل بالعربي

بوت Python لإعادة توازن المحفظة تلقائياً على منصة MEXC Spot.  
يشمل واجهة ويب عربية/إنجليزية، بوت تليجرام، وإشعارات Discord.

---

## 📋 الفهرس

1. [المتطلبات](#-المتطلبات)
2. [التثبيت السريع](#-التثبيت-السريع)
3. [متغيرات البيئة](#-متغيرات-البيئة)
4. [طرق التشغيل](#-طرق-التشغيل)
   - [Docker (الأسهل)](#1-docker-الأسهل)
   - [Systemd على سيرفر Linux](#2-systemd-على-سيرفر-linux)
   - [تشغيل مباشر بدون Docker](#3-تشغيل-مباشر-بدون-docker)
5. [واجهة الويب](#-واجهة-الويب)
6. [بوت تليجرام](#-بوت-تليجرام)
7. [إشعارات Discord](#-إشعارات-discord)
8. [أوضاع إعادة التوازن](#-أوضاع-إعادة-التوازن)
9. [تشغيل الاختبارات](#-تشغيل-الاختبارات)
10. [هيكل الملفات](#-هيكل-الملفات)
11. [أسئلة شائعة](#-أسئلة-شائعة)

---

## 📦 المتطلبات

| الأداة | الإصدار الأدنى | ملاحظة |
|--------|---------------|--------|
| Python | 3.10+ | مطلوب |
| pip | أي إصدار | مطلوب |
| Docker + Docker Compose | أي إصدار | اختياري (للتشغيل بـ Docker) |
| Node.js | 18+ | اختياري (لبناء الواجهة يدوياً) |
| حساب MEXC | — | مع صلاحية Spot Trading |

---

## ⚡ التثبيت السريع

```bash
# 1. استنساخ المشروع
git clone https://github.com/your-repo/mexc-rebalancer-bot.git
cd mexc-rebalancer-bot

# 2. نسخ ملف البيئة وتعديله
cp .env.example .env
nano .env   # أضف مفاتيح MEXC وتوكن تليجرام

# 3. تشغيل بـ Docker (أسرع طريقة)
docker compose up -d

# أو تشغيل مباشر
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

افتح المتصفح على: `http://localhost:8000`

---

## 🔑 متغيرات البيئة

أنشئ ملف `.env` في جذر المشروع:

```env
# ── مطلوب ──────────────────────────────────────────────────────────────────
MEXC_API_KEY=your_api_key_here
MEXC_SECRET_KEY=your_secret_key_here

# ── اختياري: تليجرام ────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here      # يقيّد الوصول لمستخدم واحد فقط

# ── اختياري: وضع تجريبي ─────────────────────────────────────────────────────
# false = تداول حقيقي | true = تجريبي بدون صفقات فعلية
PAPER_TRADING=false
```

### كيف تحصل على مفاتيح MEXC؟

1. سجّل دخول على [mexc.com](https://www.mexc.com)
2. اذهب إلى: **الحساب ← API Management ← إنشاء API**
3. فعّل صلاحية **Spot Trading** فقط (لا تفعّل السحب)
4. احفظ `API Key` و `Secret Key` في ملف `.env`

> ⚠️ **تحذير أمني:** لا تشارك مفاتيح API مع أحد. لا تضعها في الكود مباشرة.

### كيف تحصل على توكن تليجرام؟

1. افتح تليجرام وابحث عن `@BotFather`
2. أرسل `/newbot` واتبع التعليمات
3. انسخ التوكن وضعه في `TELEGRAM_BOT_TOKEN`
4. لمعرفة `CHAT_ID` الخاص بك: ابحث عن `@userinfobot` وأرسل له أي رسالة

---

## 🚀 طرق التشغيل

### 1. Docker (الأسهل)

```bash
# تشغيل في الخلفية
docker compose up -d

# عرض السجلات
docker compose logs -f

# إيقاف
docker compose down
```

البوت سيعمل تلقائياً عند إعادة تشغيل السيرفر (`restart: unless-stopped`).

---

### 2. Systemd على سيرفر Linux

مناسب لـ Ubuntu/Debian بدون Docker.

```bash
# تثبيت كـ service
sudo bash deploy/install.sh

# إدارة الـ service
sudo systemctl status mexc-rebalancer    # عرض الحالة
sudo systemctl restart mexc-rebalancer   # إعادة تشغيل
sudo systemctl stop mexc-rebalancer      # إيقاف
sudo journalctl -u mexc-rebalancer -f    # عرض السجلات المباشرة
```

ملف الـ service موجود في: `deploy/mexc-rebalancer.service`

---

### 3. تشغيل مباشر بدون Docker

```bash
# تثبيت المكتبات
pip install -r requirements.txt

# تشغيل الخادم
uvicorn api.main:app --host 0.0.0.0 --port 8000

# أو عبر main.py
python main.py
```

---

## 🖥️ واجهة الويب

افتح `http://localhost:8000` في المتصفح.

### الصفحات

| الصفحة | الوظيفة |
|--------|---------|
| 📊 **لوحة التحكم** | عرض المحفظة الحية، الرسوم البيانية، جدول الأصول مع عمود الفرق |
| ➕ **إنشاء بوت** | إعداد محفظة جديدة من الصفر |
| ⚙️ **الإعدادات** | تعديل الأصول والنسب ووضع إعادة التوازن |
| 🔔 **الإشعارات** | ضبط Discord Webhook وتليجرام |

### الميزات الرئيسية

- **تعديل الأصول مباشرة** من Dashboard — إضافة/حذف/تعديل بدون الذهاب لـ Settings
- **منع تكرار العملات** — خطأ أحمر فوري عند إدخال عملة مكررة (مثل SOL مرتين)
- **عمود الفرق (Deviation)** — يعرض (الحالي% - الهدف%) بألوان:
  - 🔴 أحمر = الأصل زائد عن هدفه
  - 🟢 أخضر = الأصل ناقص عن هدفه
- **زر إلغاء Rebalance** — يظهر عداد تنازلي 10 ثواني بعد الضغط على Rebalance
- **تصدير Excel** — تقرير كامل بورقتين (العمليات + أداء المحفظة)
- **Dark/Light Mode** — زر ☀️/🌙 في الشريط العلوي
- **عربي/إنجليزي** — زر `ع/EN` في الشريط العلوي

---

## 📱 بوت تليجرام

### الأوامر المتاحة

| الأمر | الوظيفة |
|-------|---------|
| `/start` | القائمة الرئيسية مع أزرار سريعة |
| `/status` | عرض حالة المحفظة الحالية مع الأسعار |
| `/rebalance` | تنفيذ إعادة توازن يدوي فوري |
| `/history` | آخر 10 عمليات إعادة توازن |
| `/stats` | إحصائيات الأداء والربح/الخسارة |
| `/export` | تصدير سجل العمليات كملف CSV |
| `/settings` | تعديل إعدادات المحفظة خطوة بخطوة |
| `/stop` | إيقاف البوت |
| `/help` | عرض قائمة الأوامر |

> **ملاحظة:** البوت يعمل داخل نفس عملية FastAPI — لو الـ API وقع، البوت يوقف معه تلقائياً.

---

## 🎮 إشعارات Discord

1. افتح سيرفر Discord الخاص بك
2. اذهب إلى: **Server Settings ← Integrations ← Webhooks ← New Webhook**
3. اختر القناة وانسخ رابط الـ Webhook
4. في واجهة الويب: **🔔 الإشعارات ← Discord ← الصق الرابط ← اختبار**

---

## ⚖️ أوضاع إعادة التوازن

### 📊 نسبة مئوية (Proportional)

البوت يفحص المحفظة كل 5 دقائق. إذا انحرف أي أصل عن هدفه بمقدار العتبة المحددة، يُنفّذ إعادة التوازن.

**العتبات المتاحة:** 1% | 3% | 5%

**مثال:**
```
هدف BTC = 60%
الحالي  = 67%  ← انحراف 7%
العتبة  = 5%   ← 7% > 5% → يُنفّذ البيع
```

### ⏰ زمني (Timed)

إعادة التوازن في وقت محدد:
- **يومي** — كل يوم في الساعة المحددة (UTC)
- **أسبوعي** — مرة كل 7 أيام
- **شهري** — مرة كل 30 يوم

### 🔓 يدوي (Unbalanced)

لا يوجد إعادة توازن تلقائي. تنفّذه يدوياً من لوحة التحكم أو عبر `/rebalance` في تليجرام.

---

## 🧪 تشغيل الاختبارات

```bash
# تثبيت pytest إذا لم يكن مثبتاً
pip install pytest

# تشغيل كل الاختبارات
pytest tests/ -v

# تشغيل اختبار محدد
pytest tests/test_smart_portfolio.py::TestValidateAllocations -v

# مع تقرير التغطية
pip install pytest-cov
pytest tests/ --cov=smart_portfolio --cov-report=term-missing
```

### ما تغطيه الاختبارات

| الوحدة | الاختبارات |
|--------|-----------|
| `validate_allocations` | عدد الأصول، مجموع النسب، الحالات الحدية |
| `load_config / save_config` | القراءة والكتابة، صحة JSON |
| `get_portfolio_value` | الحساب الصحيح، رصيد صفر، أصل USDT |
| `needs_rebalance_proportional` | فوق العتبة، تحت العتبة، عند الهدف |
| `next_run_time` | يومي/أسبوعي/شهري، التدوير للغد |
| `get_pnl` | ربح، خسارة، بدون snapshots |
| `execute_rebalance` | وضع تجريبي، ترتيب البيع قبل الشراء |
| منع التكرار | اكتشاف العملات المكررة |

---

## 📁 هيكل الملفات

```
mexc-rebalancer-bot/
│
├── api/
│   └── main.py              # FastAPI backend — كل الـ endpoints
│
├── web/
│   └── src/
│       ├── app/             # Next.js pages (layout, globals)
│       ├── components/      # React components
│       │   ├── Dashboard.tsx    # لوحة التحكم الرئيسية
│       │   ├── CreateBot.tsx    # إنشاء محفظة جديدة
│       │   ├── Settings.tsx     # الإعدادات
│       │   ├── Notifications.tsx # إعدادات الإشعارات
│       │   └── Navbar.tsx       # شريط التنقل
│       └── lib/
│           ├── api.ts       # دوال الاتصال بالـ API
│           └── i18n.ts      # ترجمات عربي/إنجليزي
│
├── tests/
│   └── test_smart_portfolio.py  # اختبارات الوحدة
│
├── deploy/
│   ├── mexc-rebalancer.service  # systemd service
│   └── install.sh               # سكريبت التثبيت
│
├── static/                  # Next.js build output (يُخدَّم بـ FastAPI)
├── database.py              # SQLite — سجل العمليات والـ snapshots
├── mexc_client.py           # MEXC REST API client (HMAC-SHA256)
├── smart_portfolio.py       # منطق إعادة التوازن
├── telegram_bot.py          # بوت تليجرام
├── main.py                  # نقطة الدخول
├── config.json              # إعدادات المحفظة (يُعدَّل من الواجهة)
├── portfolio.db             # قاعدة بيانات SQLite (تُنشأ تلقائياً)
├── Dockerfile               # Docker image
├── docker-compose.yml       # Docker Compose
├── requirements.txt         # مكتبات Python
└── .env.example             # مثال على متغيرات البيئة
```

---

## ❓ أسئلة شائعة

**س: هل البوت يدعم التداول الحقيقي؟**  
نعم. تأكد من أن `PAPER_TRADING=false` في ملف `.env` وأن مفاتيح MEXC لديها صلاحية Spot Trading.

**س: ما الحد الأدنى للاستثمار؟**  
MEXC تشترط حداً أدنى لكل صفقة (عادةً 5 USDT). يُنصح بـ 10 USDT لكل عملة على الأقل.

**س: أين تُحفظ البيانات؟**  
في ملف `portfolio.db` (SQLite) في جذر المشروع. احتفظ بنسخة احتياطية منه.

**س: هل يمكن تشغيل البوت بدون تليجرام؟**  
نعم. إذا لم تضبط `TELEGRAM_BOT_TOKEN`، يعمل البوت عبر واجهة الويب فقط.

**س: كيف أوقف البوت بأمان؟**  
- Docker: `docker compose down`
- Systemd: `sudo systemctl stop mexc-rebalancer`
- واجهة الويب: زر "⏸️ إيقاف مؤقت" في لوحة التحكم
- تليجرام: `/stop`

**س: هل يدعم عملات غير USDT؟**  
لا. جميع أزواج التداول هي `{SYMBOL}USDT` فقط.

</div>
