# Edu Manager — loyiha rejasi

> Yangi sessiya boshlanganda **avval shu faylni o'qing.** Bu yerda kelishilgan qarorlar,
> ma'lumotlar modeli, oylik formulasi, dizayn tizimi va bosqichlar holati yozilgan.
> Bosqich tugaganda "Holat" jadvalini yangilang.

## 1. Loyiha nima

Xususiy maktab uchun boshqaruv platformasi: o'quvchilar, ota-onalar, shartnomalar,
dars jadvali, to'lovlar/kassa, o'qituvchilar oyligi, yotoqxona. Mavjud (PHP'da yozilgan)
tizimdan ilhomlangan, lekin **o'z nomimiz va dizaynimiz bilan** — asl maktab nomi va logosi
ishlatilmaydi. Maktab nomi/logo/rang `SchoolSettings` modelida admin tomonidan kiritiladi.

## 2. Kelishilgan qarorlar

| Mavzu | Qaror |
|---|---|
| Stek | Python 3.13, Django 6, PostgreSQL, Django templates + HTMX (+ kerak bo'lsa Alpine.js), o'z CSS dizayn tizimi |
| Ro'yxatdan o'tish | **Yo'q.** Akkauntlarni admin yaratadi |
| Kirish | 1) Bir martalik kod (6 xona) — **SMS yoki Telegram bot** orqali 2) Login (telefon) + parol |
| Telegram | Bot faqat `/start` bosgan odamga yoza oladi → xodim botga bir marta "📱 Raqamni ulashish" qiladi (`contact.user_id == from.id` tekshiriladi) → `TelegramLink(user, chat_id)`. Dev: `run_telegram_bot` (long polling). Prod: webhook `/telegram/webhook/<secret>/` + `X-Telegram-Bot-Api-Secret-Token`. Token yo'q bo'lsa xabar terminalga chiqadi |
| Rollar (hozir) | O'qituvchi, Zavuch, Reception. Bitta foydalanuvchida bir nechta rol, yuqori panelda almashtiriladi |
| Rollar (keyin) | Direktor, Superadmin |
| Filial | Hozircha bitta (Oltiariq). `branch` FK barcha modellarda qoladi; bitta filial bo'lsa UI'da tanlagich yashirin |
| ERP / E-MAKTAB | O'quvchi o'sha tizimlarga kiritilganmi — oddiy boolean status (`in_erp`, `in_emaktab`) |
| Shartnoma | Qog'ozda imzolanadi → admin tizimga kiritadi (qoralama) → ota-ona telefoniga SMS kod → kod kiritilsa "Imzolangan". Skaner PDF biriktiriladi |
| SMS provayder | Dev: `ConsoleSMSBackend` (terminalga chiqaradi). Prod: Eskiz.uz (4-bosqichda) |
| Pul | Faqat `DecimalField`. Tranzaksiyalar o'chirilmaydi — faqat storno |
| Til | UI o'zbekcha (lotin). Ruscha tarjima keyinroq (`LANGUAGES` tayyor) |
| Muhit (2026-09-27) | Hozircha faqat lokal test. Keyin foydalanuvchining bo'sh **Contabo** serveriga deploy |
| Asosiy kirish usuli | SMS provayder ulanguncha **parol** (`LOGIN_DEFAULT_METHOD=password`). SMS/Telegram kod ixtiyoriy |
| Foydalanuvchilar | Hozir ~30 o'qituvchi. Keyin **o'quvchilar test ishlash** paneli qo'shiladi → foydalanuvchi soni keskin oshadi |
| Backup | Google Drive (rclone), **shifrlangan** holda (rclone crypt), 7 kunlik + 4 haftalik + 6 oylik; tiklash sinovi. Deploy bosqichida sozlanadi |

**Kelajak uchun muhim eslatmalar:**
- **O'quvchilar bitta IP ortida.** Kompyuter xonasidagi barcha o'quvchilar maktabning bitta tashqi IP manzilidan kiradi.
  Hozirgi IP bo'yicha limitlar (`global_ip`, `password_ip`, `otp_*_ip`) ularni bloklab qo'yadi. Test paneli bilan birga:
  maktab IP'si uchun alohida (yuqori) limit yoki akkaunt bo'yicha limitlarga o'tish, nginx `limit_req` ham shunga moslanadi.
- **Shaxsiy ma'lumotlar qonuni.** O'zbekiston "Shaxsiy ma'lumotlar to'g'risida"gi qonunining 27¹-moddasi (2021)
  O'zbekiston fuqarolarining shaxsiy ma'lumotlari (passport, JSHSHIR, telefon) O'zbekiston hududidagi serverlarda
  saqlanishini talab qiladi. Contabo (Germaniya/AQSh) va Google Drive xorijda — deploydan oldin yurist bilan aniqlash,
  kerak bo'lsa mahalliy hosting (Uzcloud va h.k.) yoki backup'ni mahalliy saqlash ko'rib chiqilsin.

## 3. O'qituvchi oyligi formulasi (sentyabr-2026 Excel bo'yicha tekshirilgan)

Ikki xil stavka (`Group.pay_scheme`):

| Turi | Qayerda | Stavka |
|---|---|---|
| `per_lesson` | Oddiy sinflar (1-D, 3-B, 5-A…) | `dars_soni × 2 400` so'm |
| `per_student` | Aniq/Ijtimoiy yo'nalish guruhlari | `120 000` so'm, keyin `deduction_percent = 15%` ushlanadi |

Har bir o'quvchi uchun:

```
Real = stavka × to'langan     / to'liq_tarif
Max  = stavka × oylik_to'lov  / to'liq_tarif
Jami = Σ Real − ushlanma(15%, faqat per_student)
```

- `to'liq_tarif` — o'quvchining chegirmasiz oylik narxi (1 750 000 yoki 1 850 000; **o'quvchiga bog'liq**, `Contract.full_tariff`).
- `oylik_to'lov` — shu oy uchun hisoblangan summa (chegirma va oy o'rtasida kelganlik hisobga olingan) = `Invoice.amount`.
- Chegirma o'qituvchi ulushini proporsional kamaytiradi. "Kun nisbati" ishlatilmaydi (doim 1.0).
- Ustama (toifa/sertifikat/til) va sinf rahbarlik — alohida qo'shiladi (namunada 0).
- Avans ≈ 30–33% oy o'rtasida; qolgani oy oxirida; kechikkan to'lovlar farqi keyingi oyga o'tadi.
- **Qabul testi:** namuna Excel bo'yicha jami Real = `4 302 985.77`, Max = `5 361 627.31`.
  Test ma'lumotlarida o'quvchi ismlari soxta bo'lishi kerak.
- Ochiq savol: 15% ushlanma sababi (Birlashma guruhi? doimiy?). Sozlanadigan qilib qoldirilgan.

## 4. Ma'lumotlar modeli (reja)

```
core        SchoolSettings(singleton), Branch, AcademicYear            ✅ 1-bosqich
accounts    User(phone login), UserRole(user, role, branch), OneTimeCode ✅ 1-bosqich
academics   Subject(name, language), Class(grade, type: regular|direction), Room,
            Group(class, subject, teacher, room, pay_scheme, rate, deduction_percent, merged_subjects),
            TimeSlot, Lesson(group, weekday, timeslot, room), HomeroomAssignment
people      Student(code STD-YYYY-NNN, …, in_erp, in_emaktab), Guardian(pinfl, passport 🔒),
            StudentGuardian(relation), Teacher(code TCH-YYYY-NNN, category, subjects, …), Certificate
contracts   Contract(number CTR-YYYY-NNN, student, year, full_tariff, monthly_fee,
            status: draft|sent|signed, signed_at, scan_pdf), Discount
billing     ChargeCategory(tuition|dorm|…), Invoice(student, category, month, amount, discount,
            waived, paid, status)  ← "To'lov grafigi"
finance     Account(cash|bank|terminal), CashSession, Payment, PaymentAllocation(payment, invoice),
            Transaction(in|out, commission, category, status, storno), ExpenseCategory(fixed|normative),
            BudgetLimit(branch, category, month), Expense
payroll     PayrollPeriod, PayrollLine, PayrollLineStudent, Penalty, SalaryPayment(advance|final|carryover)
dorm        DormRoom(beds, gender, status), DormStay, DormAttendance(B/Y/K/S), LandlordPayment
```

Zanjir: `Contract → Invoice (oyma-oy) → Payment → PaymentAllocation → Transaction`,
`Invoice.paid` → o'qituvchi oyligi.

## 4.1 Arxitektura (Clean Architecture, Django uslubida)

Har bir app ichida qatlamlar. Bog'liqlik faqat ichkariga: `views → services → selectors/models`, `services → infrastructure`.

```
apps/<app>/
  domain/          # biznes qoidalari va xatolar — Django request/HTTP'ni bilmaydi (phone.py, exceptions.py)
  models.py        # entity'lar (ORM)
  selectors.py     # o'qish so'rovlari (select_related, values_list) — biznes logika yo'q
  services/        # use-case'lar: yozish, tranzaksiya, rate limit, qoidalar (auth.py, otp.py, …)
  infrastructure/  # tashqi tizimlar: SMS, Telegram API — settings orqali almashtiriladigan backend'lar
  views.py         # yupqa HTTP qatlami: forma → servis → javob. ORM/biznes logika yozilmaydi
  forms.py, urls.py, admin.py, session.py, middleware.py
apps/common/       # umumiy: rate limiter, IP aniqlash, xavfsizlik middleware, healthz
```

Qoidalar:
- Yangi funksiya → avval servis funksiyasi + test, keyin view.
- Servislar keyword-only argumentlar oladi (`*, phone, ip`), `request` faqat zarur bo'lsa.
- Kutilgan xatolar domen istisnolari (`AuthError` avlodlari) — xabari foydalanuvchiga ko'rsatishga tayyor.
- Pul/moliya servislari `transaction.atomic()`; xatoni atomic blokdan **tashqarida** ko'tarish (hisoblagichlar rollback bo'lmasin).
- Rate limitlar faqat `settings.RATE_LIMITS` da nom bilan; kodda raqam yozilmaydi.
- Xavfsizlik va DDoS himoyasi: `docs/SECURITY.md`.

## 5. Bosqichlar va holat

| # | Bosqich | Holat |
|---|---|---|
| 1 | Poydevor: loyiha skeleti, sozlamalar, `core`, `accounts`, SMS/Telegram/parol login, rollar va rol almashtirish, layout, dark mode, testlar | ✅ tugadi (2026-09-27) |
| 1.1 | Xavfsizlik va unumdorlik: Clean Architecture qatlamlari, Redis rate limit, CSP, Argon2, open-redirect tuzatish, nginx/gunicorn/Docker prod konfiguratsiya, 43 test | ✅ tugadi (2026-09-27) |
| 2 | Ta'lim bo'limi: o'quvchilar, ota-onalar, o'qituvchilar (HR), sinflar, fanlar, guruhlar, xonalar | ⏳ keyingi |
| 3 | Dars jadvali (Zavuch tuzadi, ziddiyat tekshiruvi), o'qituvchining haftalik jadvali, chop etish | |
| 4 | Shartnomalar + SMS tasdiqlash (Eskiz), avtomatik oyma-oy Invoice, chegirmalar | |
| 5 | Kassa va moliya: sessiya, to'lov qabul qilish, tranzaksiyalar, bank/terminal, storno, qarzdorlar | |
| 6 | Xarajatlar va filial byudjeti, Reception dashboard | |
| 7 | Oylik dvigateli + testlar (Excel qabul testi), avans, qayta hisoblash, o'qituvchi paneli | |
| 8 | Yotoqxona: xonalar, joylashtirish, davomat, to'lovlar, mulkdor to'lovlari | |
| 9 | Sayqal: Excel eksport, ⌘K qidiruv, ruscha tarjima, Direktor/Superadmin | |
| 10 | O'quvchilar uchun test paneli (o'qituvchi test yaratadi, o'quvchi ishlaydi) + bitta IP ortidagi yuklama uchun limitlarni qayta sozlash | |
| 11 | Deploy (Contabo): Docker Compose, Cloudflare, SSL, shifrlangan backup → Google Drive, monitoring | |

## 6. Dizayn tizimi

- **Bitta dizayn tili** barcha rollar uchun (asl tizimdagi "daftar" va "admin shablon" aralashmasi takrorlanmaydi).
- **Uslub manbai:** BootstrapMade "NiceSchool" shablonining rang va shriftlari (2026-09-27 da tanlangan, 1-usul).
  Faqat palitra va uslub olingan — Bootstrap va shablon kodi ishlatilmaydi (litsenziya: bepul versiyada kredit havolasi shart).
- Palitra: urg'u `#08915e` (yashil), sarlavha `#2d465e`, fon `#f1f5f4`. Login chap paneli: `#1d3346` → `#08915e` gradient.
- Shriftlar: sarlavhalar **Raleway** (`lining-nums` bilan, aks holda raqamlar "eski uslub"), matn **Onest**. Poppins ishlatilmaydi (kirill yo'q). Raqamlar `tabular-nums`.
- Tokenlar: `static/css/app.css` boshida (`--bg`, `--surface`, `--heading`, `--text`, `--accent`…). Yangi rang to'g'ridan-to'g'ri yozilmaydi — faqat token.
- **Rol urg'u rangi:** `body[data-role]` → o'qituvchi = yashil `#08915e`, zavuch = ko'k `#2d6a9f`, reception = sariq `#c9761b`. Foydalanuvchi qaysi panelda ekanini rangdan biladi.
- Statistika kartalari: to'liq rangli ikon bloki (NiceSchool "Why Choose Us" kabi), hover'da ko'tariladi. Faol menyu bandida chap chiziq.
- Dark mode: tizim sozlamasi + qo'lda almashtirish (`localStorage.theme`).
- Ikonlar: `templates/partials/icons.html` SVG sprite, `{% include "partials/icon.html" with name="…" %}`.
- Komponentlar: `.btn-*`, `.input`, `.input-group`, `.segmented`, `.otp`, `.card`, `.stat`, `.empty`, `.badge`, `.dropdown`, `.toast`.
- Mobil birinchi: o'qituvchilar asosan telefondan kiradi. Sidebar ≤1024px da drawer.
- Keyin qo'shiladi: ⌘K global qidiruv, jadval komponenti (sticky header, zichlik, saqlangan filtrlar), skeleton loaderlar, ApexCharts.

## 7. Ishga tushirish

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo      # demo foydalanuvchilar → demo_credentials.txt
REDIS_URL=redis://localhost:6379/1 uv run python manage.py runserver 8000
uv run pytest
uv run ruff check .          # Bandit (S) xavfsizlik qoidalari ham yoqilgan
```

- `.env` ixtiyoriy (`.env.example` ga qarang). Default: `postgres://localhost:5432/edu_manager`.
- `REDIS_URL` bo'lmasa kesh xotirada (bitta jarayon uchun) — dev'da yetadi, prod'da Redis majburiy.
- Production: `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` (batafsil: `docs/SECURITY.md`).
- SMS va Telegram kodlari dev rejimida (token bo'lmasa) runserver terminaliga chiqadi.
- Haqiqiy Telegram bot: `.env` ga `TELEGRAM_BOT_TOKEN=...` va `TELEGRAM_BOT_USERNAME=...` (@ siz),
  so'ng alohida terminalda `uv run python manage.py run_telegram_bot`.
- Admin panel: `/admin/` (superuser `seed_demo` orqali yaratiladi).
