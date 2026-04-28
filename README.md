# MEXC Portfolio Rebalancer Bot

بوت تيليجرام لإدارة وإعادة توازن محافظ العملات الرقمية على منصة MEXC.

## المميزات

- **إنشاء بوت** — أنشئ محفظة بأي عملات ونسب (حتى 20 عملة)
- **تشغيل / إيقاف** — تحكم في كل محفظة بشكل مستقل
- **إعادة توازن تلقائية** — نسبي، مجدول، أو يدوي
- **شراء / بيع** — أوامر سوق مباشرة من تيليجرام
- **عرض الرصيد** — رصيد محفظة محددة أو الرصيد العام
- **قاعدة بيانات** — PostgreSQL (Supabase) أو SQLite

## التشغيل

```bash
pip install -r requirements.txt
python main.py
```

## متغيرات البيئة

| Variable | مطلوب | الوصف |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | توكن البوت من BotFather |
| `MEXC_API_KEY` | ✅ | مفتاح MEXC API |
| `MEXC_SECRET_KEY` | ✅ | سيكريت MEXC |
| `DATABASE_URL` | لا | رابط PostgreSQL — يستخدم SQLite إذا لم يُحدد |
| `TELEGRAM_CHAT_ID` | لا | تقييد الوصول لمستخدم واحد |
| `PAPER_TRADING` | لا | `true` لتفعيل وضع المحاكاة |

## أوامر تيليجرام

| الأمر | الوصف |
|---|---|
| `/start` أو `/menu` | القائمة الرئيسية |
| `/done` | حفظ البوت بعد إضافة العملات |

## هيكل الملفات

```
main.py              — نقطة البداية
engine.py            — إدارة دورات إعادة التوازن
bot/telegram_bot.py  — واجهة تيليجرام
mexc_client.py       — MEXC REST API client
smart_portfolio.py   — منطق إعادة التوازن
database.py          — طبقة قاعدة البيانات
config.json          — إعدادات افتراضية
```

## النشر على Railway

1. أنشئ مشروعاً جديداً على Railway واربطه بهذا الريبو
2. أضف المتغيرات: `TELEGRAM_BOT_TOKEN`, `MEXC_API_KEY`, `MEXC_SECRET_KEY`, `DATABASE_URL`
3. Railway سيبني ويشغل البوت تلقائياً عبر `python main.py`
