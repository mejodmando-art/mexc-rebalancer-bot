<div align="center">

# 🤖 MEXC Trade Bot

**بوت تيليجرام لإدارة المحفظة والتداول على منصة MEXC**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://railway.app)

</div>

---

## ✨ الميزات

### إدارة المحفظة
| الميزة | التفاصيل |
|--------|----------|
| 🗂 **محافظ متعددة** | رأس مال وتوزيع مستقل لكل محفظة |
| ⚖️ **إعادة التوازن** | يدوي أو تلقائي بجدولة زمنية مرنة |
| 🎯 **حد الانحراف** | يُطبَّق تلقائياً على جميع العملات |
| 🚨 **بيع طوارئ** | بيع فوري لعملة واحدة أو الكل |
| 📋 **سجل العمليات** | تتبع كامل لجميع عمليات التوازن |

### الاستراتيجيات
| الاستراتيجية | الوصف |
|-------------|-------|
| ⚡ **Scalping** | Smart Liquidity Flow — يسكان السوق كل 15 دقيقة |
| 🐋 **Whale** | Order Flow Strategy — يتتبع حركة الحيتان |
| 🔲 **Grid Bot** | شبكة أوردرات تلقائية بين نطاق سعري محدد |

---

## ⚙️ الإعداد

### 1. متغيرات البيئة

انسخ `.env.example` إلى `.env` وعدّل القيم:

```bash
cp .env.example .env
```

| المتغير | الوصف | مطلوب |
|---------|-------|-------|
| `TELEGRAM_BOT_TOKEN` | توكن البوت من @BotFather | ✅ |
| `ALLOWED_USER_IDS` | معرّف تيليجرام (من @userinfobot) | ✅ |
| `DATABASE_URL` | رابط PostgreSQL للحفظ الدائم | اختياري |

### 2. تشغيل محلي

```bash
pip install -r requirements.txt
python main.py
```

### 3. النشر على Railway

1. Fork المستودع
2. أنشئ مشروعاً جديداً على Railway واربطه بالمستودع
3. أضف المتغيرات: `TELEGRAM_BOT_TOKEN` و `ALLOWED_USER_IDS`
4. اختياري: أضف **PostgreSQL** من قائمة Databases للحفظ الدائم
   - بعد الإضافة، اربط `DATABASE_URL` من خدمة PostgreSQL بخدمة البوت

---

## 📌 إضافة العملات

**بالرموز فقط — ثم اختر طريقة التوزيع:**
```
BTC ETH SOL USDT BNB
```

**بالنسب مباشرة:**
```
BTC=40
ETH=30
SOL=20
USDT=10
```

طرق التوزيع المتاحة:
- ⚖️ **متساوٍ** — 100% ÷ عدد العملات
- 📈 **حسب السوق** — بناءً على حجم التداول
- ✏️ **يدوي** — تحدد النسبة بنفسك

---

## 🗄️ قاعدة البيانات

البوت يستخدم **SQLite** افتراضياً (مناسب للتطوير المحلي).  
على Railway، البيانات **تُحذف عند كل إعادة تشغيل** — أضف PostgreSQL للحفظ الدائم.

---

<div align="center">
  <sub>Built with python-telegram-bot · ccxt · Railway</sub>
</div>
