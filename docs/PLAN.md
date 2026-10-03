# Edu Manager — loyiha rejasi

> Yangi sessiya boshlanganda **avval shu faylni o'qing.** Bu yerda kelishilgan qarorlar,
> ma'lumotlar modeli, oylik formulasi, dizayn tizimi va bosqichlar holati yozilgan.
> Bosqich tugaganda "Holat" jadvalini yangilang.

## 1. Loyiha nima

Xususiy maktab uchun boshqaruv platformasi: o'quvchilar, ota-onalar, shartnomalar,
dars jadvali, to'lovlar/kassa, o'qituvchilar oyligi, yotoqxona. Mavjud (PHP'da yozilgan)
tizimdan ilhomlangan, lekin **o'z nomimiz va dizaynimiz bilan** — asl maktab nomi va logosi
ishlatilmaydi. Maktab nomi/logo/rang `SchoolSettings` modelida admin tomonidan kiritiladi.

**Referens skrinshotlar:** asl tizimning 51 ta skrinshoti lokal `reference/screenshots/` papkasida
(`INDEX.md` — ro'yxat). Gitignore'da: rasmlarda haqiqiy shaxsiy ma'lumotlar bor.

## 2. Kelishilgan qarorlar

| Mavzu | Qaror |
|---|---|
| Stek | Python 3.13, Django 6, PostgreSQL, Django templates + HTMX (+ kerak bo'lsa Alpine.js), o'z CSS dizayn tizimi |
| Ro'yxatdan o'tish | **Yo'q.** Akkauntlarni admin yaratadi |
| Kirish | 1) Bir martalik kod (6 xona) — **SMS yoki Telegram bot** orqali 2) Login (telefon) + parol |
| Telegram | Bot faqat `/start` bosgan odamga yoza oladi → xodim botga bir marta "📱 Raqamni ulashish" qiladi (`contact.user_id == from.id` tekshiriladi) → `TelegramLink(user, chat_id)`. Dev: `run_telegram_bot` (long polling). Prod: webhook `/telegram/webhook/<secret>/` + `X-Telegram-Bot-Api-Secret-Token`. Token yo'q bo'lsa xabar terminalga chiqadi |
| Rollar (hozir) | O'qituvchi, Zavuch, Reception. Bitta foydalanuvchida bir nechta rol, yuqori panelda almashtiriladi |
| Rollar | Direktor (2026-10-03): **nazorat + rahbar qarorlari**, o'ziga tayinlangan filial. Hamma bo'limni ko'radi; o'zgartiradi faqat byudjet limitlari, oylik sozlamalari, xodimlar kirishi (rolni yoqish/o'chirish). Server: direktor POST'i faqat `@director_can_write` view'larda (`accounts.permissions.role_required`) |
| Superadmin | `is_superuser`. Rol biriktirilmaydi — `/superadmin/` "Panel almashtirish": (1) **rol sifatida ko'rish** — virtual rol (Reception/Zavuch/O'qituvchi × filial), bazaga yozilmaydi; (2) **xodim qiyofasida kirish** — `ImpersonationMiddleware` so'rov davomida `request.user` ni almashtiradi, `request.impersonator` — haqiqiy superadmin, sessiya saqlanadi. Qizil ogohlantirish chizig'i; "Chiqish" qiyofadan chiqaradi (tizimdan emas). Admin/boshqa superadmin qiyofasiga kirilmaydi, ichma-ich impersonation yo'q, impersonation paytida Django admin yopiq. `ImpersonationLog` (o'chirilmaydi) + har bir POST `security` logida |
| Filial | Hozircha bitta (Oltiariq). `branch` FK barcha modellarda qoladi; bitta filial bo'lsa UI'da tanlagich yashirin |
| ERP / E-MAKTAB | O'quvchi o'sha tizimlarga kiritilganmi — oddiy boolean status (`in_erp`, `in_emaktab`) |
| Shartnoma | Qog'ozda imzolanadi → admin tizimga kiritadi (qoralama) → ota-ona telefoniga SMS kod → kod kiritilsa "Imzolangan". Skaner PDF biriktiriladi. Kod `OneTimeCode.subject="contract:<id>"` ga bog'langan (aka-uka shartnomalari kodlari almashmaydi). SMS matnida o'quvchi, raqam va oylik summa. Bir o'quvchiga bir o'quv yilida bitta amaldagi shartnoma |
| Tarif | `SchoolClass.monthly_tariff` (sukut; rus sinflari 1 850 000, qolganlari 1 750 000). Shartnomada `full_tariff` va `discount_percent` (sababi majburiy) → `monthly_fee` so'mgacha yaxlitlanadi |
| Qabul oqimi | Qabul formasi (o'quvchi + asosiy ota-ona) → avtomatik shartnoma formasiga o'tadi → SMS tasdiqlash |
| Ota-ona | Alohida yaratilmaydi — faqat o'quvchiga biriktirilganda. Takrorlanishga qarshi: avval JSHSHIR (blind index), keyin telefon + familiya; topilsa mavjud yozuvga bog'lanadi, bo'sh maydonlari to'ldiriladi, mavjudlari ustiga yozilmaydi |
| Shaxsiy ma'lumot | Passport/JSHSHIR — Fernet shifrlash (`FIELD_ENCRYPTION_KEYS`), qidirish blind index (`FIELD_INDEX_KEY`). Ekranda niqoblangan (`\|mask`). Shartnoma skanerlari `PRIVATE_MEDIA_ROOT` da (URL yo'q, faqat ruxsatli view orqali) |
| Moliya | Qoldiq hech qayerda saqlanmaydi — `Transaction` jurnalidan hisoblanadi (`ledger.balance`). Yozuvlar o'chirilmaydi: xato to'lov → storno (teskari tranzaksiya), kassa farqi → "Kassa tafovuti" yozuvi. To'lov eng eski oydan FIFO taqsimlanadi, qarzdan ortiq qabul qilinmaydi. Naqd pul (to'lov/xarajat/storno) faqat ochiq kassa sessiyasida. Terminal komissiyasi 0.2% (`TERMINAL_COMMISSION_PERCENT`). Moliya sahifalari faqat Reception'ga. **2026-09-29:** Zavuch o'quvchi va ota-ona kartasidagi to'lov ma'lumotini (grafik, to'lovlar tarixi, qarz, kvitansiya, grafik Excel'i) **faqat ko'radi** — to'lov qabul qilish, storno, grafik yaratish, o'qishdan chiqarish va Kirim/Yotoqxona bo'limlari faqat Reception'da (`FINANCE_VIEW_ROLES` / `finance_edit`) |
| O'qishdan chiqish (2026-09-27) | Shartnomasi/to'lovi bor o'quvchi **to'g'ridan-to'g'ri o'chirilmaydi** → "O'qishdan chiqarish" hisob-kitobi (`finance.services.withdrawal`, faqat Reception): chiqish oyida o'qigan kunlar `oylik × kunlar / oy_kunlari` (chiqish kuni ham kiradi, mingga pastga), keyingi oylar bekor, yotoqxona o'z sanasi bilan; to'langan pul FIFO qayta taqsimlanadi — ortig'i qaytariladi (`Transaction` REFUND, naqd — ochiq kassa va yetarli qoldiq), kami qarz bo'lib qoladi. Shartnoma yopiladi, o'quvchi «Ketgan». `Withdrawal` + `WithdrawalLine` — audit, o'chirilmaydi; keyin storno yo'q. Hech tarixi yo'q o'quvchigina butunlay o'chiriladi |
| To'lov grafigi (2026-09-28) | **Aralash usul:** imzolanganda faqat joriy oygacha yaratiladi; har kuni cron `manage.py generate_monthly_invoices` (idempotent) oy boshida yangi oyni qo'shadi; oldindan to'lov uchun Reception "Grafik" oynasida keyingi oylarni yaratadi (boshlanish oyi, nechta oy, muddat kuni; bo'shliq va shartnoma muddatidan tashqari oy yo'q). To'lov faqat yaratilgan oylar qarzigacha. Birinchi oyning muddati kelgan kundan kamida +10 kun |
| Xarajatlar va byudjet (2026-09-29) | Hozircha **yopiq** — ma'lumot faqat rahbariyat uchun. Menyu bandi "Bu bo'lim tayyorlanmoqda" sahifasini ochadi, `/budget/` ham o'sha yerga yo'naltiradi, dashboard'dagi "Limitlar" tugmasi yashirin. Ochish: `settings.BUDGET_PAGE_ENABLED = True` |
| Proratsiya | Oyning 1–5-kuni kelgan — to'liq oy; keyin — `oylik × qolgan_kun / oy_kunlari`, mingga pastga yaxlitlanadi (Excel: 933 000, 735 000, 525 000, 863 000 — testda). To'lov muddati — har oyning 10-sanasi |
| Grafiklar | Tashqi JS kutubxonasiz: serverda SVG (`apps/common/charts.py`), kenglik/koordinata — SVG atributlari (CSP inline style'ni taqiqlaydi). SVG ichida `{% localize off %}` (o'zbek lokali o'nli vergul qo'yadi) |
| SMS matni | Faqat GSM-7 belgilar (NBSP va h.k. yo'q) — aks holda Unicode'ga o'tib narx 2–3 baravar oshadi |
| SMS provayder | Dev: `ConsoleSMSBackend` (terminalga chiqaradi). Prod: Eskiz.uz (4-bosqichda) |
| Pul | Faqat `DecimalField`. Tranzaksiyalar o'chirilmaydi — faqat storno |
| Dizayn (2026-09-29) | **Apple HIG uslubi** — tizim shrifti (SF Pro / Inter), Apple tizim ranglari, systemBlue urg'u + rol belgisi, suzuvchi shaffof sidebar, telefonda pastki tab bar va sheet panellar. Batafsil — 6-bo'lim |
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
- **Ustamalar (foydalanuvchi qarori, 2026-10-02; asl jadvaldagi raqamlardan tekshirilgan):**
  Real oylik = Asosiy (+ belgilangan oylik) + Toifa + Sertifikat + Til + S/R − Jarimalar.
  Toifa — toifa foizi × **darsbay** qismi (2-toifa 10%, qolganlari sozlamada); Sertifikat — 30% × amaldagi
  sertifikat **fanidan** tushgan qism (fani yo'q sertifikat — hamma fan); Til — 15% × ta'lim tili o'zbekcha bo'lmagan
  sinflar qismi; S/R — **o'quvchi boshiga stavka × to'lov ulushi** (sukut 30 000; asl sahifadan: sinflar bo'yicha
  max 995 006 / 34, 663 000 / 24, 458 777 / 16 o'quvchi — summa o'quvchi soniga bog'liq, 2026-10-02 tuzatildi);
  Jarimalar = guruh ushlanmasi (15%) + qo'lda jarima (bekor qilinadi, o'chirilmaydi). Foiz/summalar —
  `PayrollSettings` (filial), Zavuch «Sozlamalar» panelida.

## 4. Ma'lumotlar modeli (reja)

```
core        SchoolSettings(singleton), Branch, AcademicYear            ✅ 1-bosqich
accounts    User(phone login), UserRole(user, role, branch), OneTimeCode ✅ 1-bosqich
academics   Subject(name, language), Class(grade, type: regular|direction), Room,
            Group(class, subject, teacher, room, pay_scheme, rate, deduction_percent, merged_subjects),
            TimeSlot(number, start, end), Lesson(group, subject, teacher, weekday, slot, room, valid_from, valid_to) ✅
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
| — | **Tartib (2026-09-27, foydalanuvchi qarori): avval Reception → keyin Zavuch → keyin O'qituvchi paneli** | |
| 2R | **Reception: qabul** — o'quvchilar (ro'yxat/qidiruv/filtr/ERP·E-maktab), qabul formasi (o'quvchi + ota-ona bitta tranzaksiyada), ota-onalar (takrorlanishga qarshi), shartnomalar (tarif, chegirma, chop etish, SMS kod bilan tasdiqlash, PDF skaner), 69 test | ✅ tugadi (2026-09-27) |
| 2R.2 | **Reception: moliya (yadro)** — to'lov grafigi (imzolanganda avtomatik, proratsiya), to'lov qabul qilish (FIFO, storno), kassa sessiyasi (tafovut yozuvi), xarajatlar, byudjet limitlari, Reception dashboard (SVG grafiklar), 89 test | ✅ tugadi (2026-09-27) |
| 2R.2a | O'quvchilar ro'yxati: "Filtr qo'shish" menyusi (o'quv yili, sinf, grade, tarif, jins, status, qabul sanasi, ERP, E-maktab), Excel eksport (`apps/common/excel.py`, formula-injection himoyasi), qator amallari (ko'rish / to'lovlar / tahrir / o'chirish — tarixi bor o'quvchi o'chirilmaydi, «Ketgan»ga o'tkaziladi), ranglar uyg'unligi. **O'quvchi kartasi**: "Akademik" (profil, hujjatlar 🔒 niqoblangan, yashash manzili, vasiylar, aka-uka/opa-singillar — umumiy vasiy orqali, o'quv faoliyati) va "To'lov" (faqat Reception: hisoblangan/to'langan/qarz joriy oygacha, to'lov grafigi + Excel, to'lovlar tarixi, shartnomalar); `Student` ga passport/JSHSHIR/guvohnoma (shifrlangan) va viloyat/tuman/mahalla. **Tahrirlash sahifasi**: yig'iladigan bo'limlar (shaxsiy, hujjatlar — metrika/passport, o'quv ma'lumotlari, o'quv yili va sinf, tarif — faqat ko'rish, vasiylar, shartnomalar); o'quvchi + vasiylar + yangi vasiy bitta tranzaksiyada (`admission.update_profile`), vasiyni ajratish (asosiy ajratilmaydi), umumiy vasiy "N o'quvchi" ogohlantirishi, `Guardian.position`; qabul formasi ham shu bo'limlardan, 126 test | ✅ tugadi (2026-09-27) |
| 2R.2c | O'quvchi kartasidan vasiy ✏️ → to'liq tahrirlash (`#g<id>`); shartnomadan "Orqaga" — kelgan joyga (`?next=` + bo'lim langari, `common.http.safe_next`); **o'qishdan chiqarish hisob-kitobi** (ko'rib chiqish → tasdiqlash → hujjat), o'chirish oqimi unga bog'landi, 134 test | ✅ tugadi (2026-09-27) |
| 2R.2d | To'lov grafigi oyma-oy (aralash usul) + "Grafik" oynasi, cron buyrug'i, birinchi oy muddati muhlati, 139 test | ✅ tugadi (2026-09-28) |
| 2R.2e | **Ota-onalar**: ro'yxat faqat ko'rish (✏️ yo'q, alohida tahrirlash sahifasi olib tashlandi — vasiy faqat o'quvchini tahrirlash sahifasida o'zgartiriladi), "Filtr qo'shish" (munosabat, holat), Excel (JSHSHIR/passport'siz), 5 ta statistika; **ota-ona kartasi**: farzandlar (qarz/to'langan, Akademik/To'lov), qarzdorliklar (asl tizimdagidek barcha oylar: tarif, muddat, holat) va to'lovlar tarixi (# / TRX, kvitansiya) — faqat Reception; **kvitansiya chop etish** (`finance:payment_receipt`, A5, storno belgisi); munosabatlar asl tizimdagidek: Ota, Ona, Buva, Buvi, Tog'a, Xola, Boshqa ("Boshqa vasiylar" statistikasi — ota/onadan tashqari hammasi), 145 test | ✅ tugadi (2026-09-28) |
| 2R.2f | **Shartnomalar filtri** (asl tizimdagidek: Barcha yillar / Barcha sinflar / Barcha holatlar + "Muddati o'tgan"); filtr paneli umumiy qism — `partials/filter_bar.html` + `common.forms.filter_menu` (o'quvchilar, ota-onalar, shartnomalar), 146 test | ✅ tugadi (2026-09-28) |
| 2R.2g | **Kirim → Kassa paneli** (asl tizimdagidek): naqd / bank+terminal / umumiy qoldiq, kassa sessiyasi (ochilish, oxirgi harakat, boshlang'ich, kutilgan naqd; sanab yopish), bugungi kirim / sof balans (chiqim/kirim nisbati, oylik sof) / chiqim, to'lov turlari kesimi, kun tanlash (`?date=`), `short_money` (474.3 mln); shartnomalar Excel; menyu guruhi "Kirim", 149 test | ✅ tugadi (2026-09-29) |
| 2R.2h | **Kirim → To'lovlar** ro'yxati: statistika (jami kirim, soni, qaytarilgan — o'qishdan chiqishda, storno soni), doim ochiq filtr (qidiruv, sanadan–sanagacha — sukut bugun, to'lov turi, sinf, yaratuvchi), Excel, kvitansiya, 151 test | ✅ tugadi (2026-09-29) |
| 2R.2i | **Kirim → Tranzaksiyalar**: 5 statistika (kirim, chiqim, sof, bank komissiyasi, soni), to'lov turlari bo'yicha (komissiya % bilan), filtr (qidiruv — izoh/kvitansiya/TRX-ID, turi, kategoriya, to'lov turi, karta tarmog'i, status, yaratuvchi, sana, summa dan), jami/sof total, Excel. Filtr asl tizimdagidek: kategoriya va to'lov turi — ko'p tanlovli (`partials/multiselect.html`), kategoriyalarda o'quvchi / yotoqxona to'lovi ajratilgan, karta tarmog'iga Mastercard qo'shildi, status: muvaffaqiyatli / bekor qilingan / storno, 152 test | ✅ tugadi (2026-09-29) |
| 2R.2j | **Kirim → Bank hisobi**: davr filtri (sukut: oy boshi — bugun), umumiy bank qoldig'i (davr + barcha vaqt), bank o'tkazmalari, terminal (net, komissiya), ichki o'tkazmalar, tafsilot jadvali (30 tadan), 153 test | ✅ tugadi (2026-09-29) |
| 2R.2k | **Kirim → To'lov grafiklari**: 6 statistika (jami hisoblangan, chegirma, kechilgan, to'langan, qoldiq = jami − kechilgan − to'langan, soni), "Filtr qo'shish" (sinf, o'quv yili, oy, holati — muddati o'tgan ham, o'quvchi holati), qidiruv, Excel, qisman to'langan qatorlar ajratilgan, 20 tadan. Holati: kutilmoqda / qisman / to'langan / muddati o'tgan / kechirilgan / bekor qilingan; o'quvchi holatlari asl tizimdagidek 6 ta (faol, nofaol, bitirgan, o'qishdan chiqarilgan, ta'tilda, ketgan), 161 test | ✅ tugadi (2026-09-29) |
| 2R.2l | **Kirim → Qarzdorlar**: faqat kelgan oylar (joriy oygacha) bo'yicha qarz, o'quvchi bir qatorda (qarzdor oylar, jami, to'langan, qoldiq, oxirgi to'lov), filtr (sinf, o'quv yili, oy, holat), Excel; yon panel `<dialog class="side-panel">`: ℹ️ ma'lumot (grafik) va 💳 to'lov (qarzlar ro'yxati, summa, usul, sana, izoh, kvitansiya chop etish → to'g'ridan-to'g'ri kvitansiyaga, keyin ro'yxatga qaytadi). To'lov sanasi: kelajak yo'q, naqd faqat bugun, karta/o'tkazma ≤ `PAYMENT_BACKDATE_DAYS` (31) kun oldin, 163 test | ✅ tugadi (2026-09-29) |
| 3Z.1 | **Zavuch: bosh sahifa va o'quvchilar** — Zavuch dashboardi (faqat ta'lim: faol o'quvchilar, o'qituvchilar, sinflar, tasdiqlanmagan shartnomalar, ERP/E-maktab'ga kiritilmaganlar, o'sish trendi, jinsi, sinflar bo'yicha, oxirgi qabul qilinganlar; `ROLE_DASHBOARDS`). **Qabul — bitta forma** (asl tizimdagidek): shaxsiy, hujjat, vasiylar Ota / Ona / Olib keluvchi (yoqib-o'chiriladi, JSHSHIR va passport majburiy), moliya (o'quv yili, sinf → grade va tarif, boshlanish, chegirma % + sabab, jonli hisob), shartnoma vasiysi → o'quvchi + vasiylar + shartnoma qoralamasi bitta tranzaksiyada (`admission.admit_with_contract`), keyin SMS uchun shartnoma sahifasi. **Manzil ma'lumotnomasi**: `District` (206 ta tuman, migration), `Mahalla` (admin yoki forma orqali birinchi kiritilganda), viloyat → tuman bog'liq tanlagich, mahalla — taklifli matn. Ro'yxatga "Jins" ustuni va "Ro'yxat" (chop etish, sinf bo'yicha). Vasiy takrorlanishi: JSHSHIRi boshqa bo'lsa telefon+familiya mos kelsa ham yangi odam. Asl tizimdagi "Chegirma turi" va "Shablon" qo'shilmadi (tur/shablon ro'yxati kelishilmagan), 182 test | ✅ tugadi (2026-09-29) |
| 3Z.2 | **Zavuch: Sinflar va guruhlar** (`apps.academics`: selectors / services / forms / views) — bitta sahifada ikki ko'rinish: sinflar jadvali (turi va til, sinf rahbari, xona, o'quvchilar/sig'im, guruhlar, tarif) va guruh kartalari (o'qituvchi panelidagi "Guruhlarim" mazmuni: kod, fanlar, daraja, to'lov sxemasi, Birlashma, o'qituvchilar, o'quvchilar/sig'im, xona); 4 statistika, filtr (o'quv yili — sukut joriy, turi, til), qidiruv. **Sinf**: qo'shish/tahrirlash (oddiy sinfda daraja majburiy, yo'nalishda yo'q; sig'im faol o'quvchilardan kam emas; nom yil ichida takrorlanmaydi), sahifasi (o'quvchilar, guruhlar, chop etish ro'yxati), o'chirish — tarixi bo'lsa faolsizlantiriladi. **Guruh**: sinf, kod, turi (butun sinf / tanlov), daraja, fanlar + o'qituvchilar (bir nechta — Birlashma), to'lov sxemasi (darsbay / belgilangan summa + ushlanma; tur tanlanganda sukut 2 400 yoki 120 000 + 15%), xona, sig'im. Butun sinf a'zolari sinfdan olinadi; tanlov guruhiga o'quvchi qo'shish (oynada: shu sinfdan / barcha sinflardan), chiqarish — `left_at` bilan tarixda qoladi (oylik uchun), qayta qo'shilsa tiklanadi. O'quvchi kartasida guruhlar = faol a'zoliklar + sinfining butun sinf guruhlari. Fanlar, xonalar, o'qituvchilar hozircha admin orqali (O'qituvchilar HR bo'limi keyin), 191 test | ✅ tugadi (2026-09-30) |
| 3Z.3 | **Shartnomalar: matn va shablonlar** — `ContractTemplate` (nom, matn, faol, sukut), belgilash: `#` sarlavha, `##` bo'lim, `###`, `>>` o'ngga, `-` ro'yxat, `**qalin**`, o'rinbosarlar `{{ vasiy }}`… (26 ta, `contracts.domain.document`; hamma qiymat escape qilinadi, noma'lum o'rinbosar saqlashda rad etiladi). Sukut shablon — maktabning haqiqiy shartnoma matni (foydalanuvchi bergan, 2026-09-30; shaxsiy va maktabga xos joylar o'rinbosarga almashtirilgan, imlo xatolari tuzatilgan, 5.3-bandga oylik to'lov qo'shilgan) — `contracts/default_template.txt` → migration. **Rekvizitlar**: `SchoolSettings.legal_name`, `Branch` — direktor, H/R, bank, MFO, STIR (admin panel → Filiallar). **Muhr**: imzolanganda matn va qiymatlar `Contract.signed_body/signed_data` ga yoziladi — keyin shablon yoki rekvizit o'zgarsa ham imzolangan matn o'zgarmaydi. Shartnoma sahifasi asl tizimdagidek: chapda ma'lumot va imzo (sana, imzolovchi, telefon, SMS-OTP), o'ngda to'liq matn + rekvizitlar; «PDF / Chop etish» — shu matn A4'da (brauzerda «PDF sifatida saqlash»). Shablon tanlash — qabul formasi va shartnoma formasida. «Shablonlar» sahifasi (Reception, Zavuch), 194 test | ✅ tugadi (2026-10-01) |
| 3Z.4 | **"Yangi shartnoma" sahifasi** (`/contracts/new/`, asl tizimdagidek): o'quvchi — qidiruvli ro'yxat (faqat shu o'quv yilida amaldagi shartnomasi yo'q faol o'quvchilar), vasiy — tanlangan o'quvchining vasiylaridan (bo'sh — asosiy vasiy; begona vasiy rad etiladi), shablon, o'quv yili, tarif (sinf tarifidan avtomatik), chegirma, boshlanish (bo'sh — qabul sanasi / o'quv yili boshi). O'quvchi kartasidagi "Shartnoma tuzish" ham shu sahifa (o'quvchi tanlangan holda); amaldagi shartnoma bo'lsa — o'shanga o'tadi, 196 test | ✅ tugadi (2026-10-01) |
| 3Z.5 | **Dars jadvali** (`academics`: `TimeSlot`, `Lesson`, `services/timetable.py`). Foydalanuvchi qarorlari (2026-10-01): **tarix saqlanadi** — dars `valid_from`–`valid_to` bilan; o'zgarish "qaysi sanadan" kiritiladi (eski yopiladi, yangisi ochiladi, boshlanmagan dars o'chiriladi) → o'tgan haftalar va darsbay oylik o'zgarmaydi; **ziddiyat — qat'iy taqiq**: bir kun+dars raqamida va kesishgan davrda guruh, o'qituvchi, xona, sinf (ikki butun-sinf darsi), o'quvchi (guruh a'zolari kesishsa) band bo'lolmaydi (`select_for_update` bilan); **qo'ng'iroqlar** — sukut 8 dars × 50 daqiqa (08:30, 09:25, 10:20, 11:20, 12:15, 13:05, 14:00, 14:55; asl jadvaldan), «Qo'ng'iroqlar» panelida har biri o'zgartiriladi (ustma-ust tushmaydi; darsi bor vaqt olib tashlanmaydi). Hafta 6 kun (Dush–Shan). Dars = guruh + fan + o'qituvchi (yozuvda saqlanadi): guruhda o'qituvchi almashsa darslar bugundan yangisiga bo'linadi, darsi bor fanni guruhdan olib bo'lmaydi. Sahifa: sinf / o'qituvchi / xona bo'yicha haftalik to'r (sanalar bilan, hafta varaqlash), katakda "+" → yon panelda guruh → fan → xona → sana; dars → ma'lumot va «qaysi sanadan olib tashlash». Sukut sana — ko'rsatilgan hafta dushanbasi; sinf jadvali bo'sh bo'lsa — o'quv yili boshi. Chop etish (A4 yotiq). `selectors.lesson_count` — davrdagi darslar soni (darsbay oylik uchun; bayramlar hali hisobga olinmaydi), 205 test | ✅ tugadi (2026-10-01) |
| 3Z.6 | **Dars jadvali — sudrab qo'yish** (asl tizimdagidek): sinf fanlari kartalari (`GroupSubject.hours_per_week` — haftalik soat limiti, guruh formasida), karta — fan, soat, o'qituvchi, xona [sinf/guruh xonasi], `qo'yilgan / limit`; limit tugasa karta o'chadi; jami `N / M soat`. **Hovuz** — bir fan sinfning bir nechta tanlov guruhida (Ingliz tili × 3 guruh): bitta karta tashlansa hamma guruh darsi bir vaqtda qo'yiladi (biri ziddiyatli bo'lsa — hech biri). Jadvaldagi darsni boshqa katakka sudrab ko'chirish (eski yopiladi, yangi ochiladi — bitta tranzaksiya). **OBED** — `TimeSlot.is_break` (Qo'ng'iroqlar panelida belgilanadi, dars qo'yilmaydi, darsi bor vaqt tanaffus qilinmaydi). Xona: guruh xonasi, bo'lmasa sinf xonasi. Excel (joriy ko'rinish) va "Barcha sinflar" Excel'i. Qo'lda qo'shish ("+") saqlanib qoldi. Foydalanuvchi fikri bo'yicha: kartalar paneli yopishqoq (ixcham), **bosib qo'yish** (karta → katak, tanlov saqlanadi), sudraganda avtomatik aylantirish, qo'yilgach joy tiklanadi, dars panelida "Boshqa katakka ko'chirish", 209 test | ✅ tugadi (2026-10-01) |
| 3Z.7 | **Xodimlar (HR) → O'qituvchilar** (Zavuch): 4 statistika (jami, faol, ta'tilda, bo'shatilgan), qidiruv (ism, kod, telefon), "Filtr qo'shish" asl tizimdagidek — turi, status, fan, jinsi, toifa; jadval: F.I.Sh. + kod + fan teglari, turi, telefon, holat (qatorda o'zgartiriladi), amallar (ko'rish, dars jadvali). `Teacher`ga **turi** (O'qituvchi / Koordinator / Yordamchi o'qituvchi), holatga **Nofaol**, **toifa** ro'yxatga o'tkazildi (1-toifa, 2-toifa, Mutaxassis, Oliy toifa; eski matn migration'da ko'chirildi). Nofaol/Bo'shatilgan o'qituvchi guruh, sinf rahbarligi va jadvalga tanlanmaydi; faol guruh fani yoki darsi bor o'qituvchini bo'shatib/nofaol qilib bo'lmaydi (avval guruhda almashtiriladi). O'qituvchi sahifasi: ma'lumotlar, haftalik soat, guruhlari, sinf rahbarligi. 213 test | ✅ tugadi (2026-10-02) |
| 3Z.8 | **O'qituvchini qo'shish / tahrirlash** (asl tizimdagidek bo'limlar): Asosiy (filial, turi, status, toifa), Shaxsiy (F.I.Sh. — `User`da, tug'ilgan sana, jinsi, oilaviy holati), Aloqa va hujjatlar (telefon — login, email, pasport seriya+raqam, JSHSHIR 🔒, manzil, "Ish staji yozilsinmi?", belgilangan oylik), Kasbiy (ma'lumoti, mutaxassisligi, tajriba, dars tillari, ishga qabul, shartnoma muddati, o'qitadigan fanlar — qidiruvli ro'yxat, izoh), **Sertifikatlar** (`Certificate`: turi — milliy/IELTS/CEFR/TOEFL/boshqa, fan, raqam, muddat, ball, kim bergan; formset bilan qo'shish/olib tashlash). Yangi o'qituvchi: `User` + O'qituvchi roli; telefon boshqa o'qituvchida bo'lsa xato, profili yo'q xodimda bo'lsa unga bog'lanadi. **Asl tizimdagi "parol = telefon" takrorlanmadi** (xavfsiz emas) — tasodifiy vaqtinchalik parol bir marta ko'rsatiladi. Ochiq: toifa ustamasi foizlari (asl: "2-toifa (10%)") — boshqa toifalar foizi aniqlanmagan, oylik bosqichida, 216 test | ✅ tugadi (2026-10-02) |
| 3Z.9 | **O'qituvchi sahifasi** (asl tizimdagidek): sarlavha kartasi (holat, kod, filial, telefon, ★ toifa, «Tahrirlash», «Orqaga»), 4 statistika (Fanlar, Sertifikatlar, Tajriba, Ishga qabul), bo'limlar `?tab=`: **Ma'lumotlar** (Shaxsiy / Hujjatlar / Ish ma'lumotlari — yig'iladigan kartalar, holatni shu yerda o'zgartirish), **Moliya** (belgilangan oylik, haftalik yuklama, ish staji, guruhlar bo'yicha yuklama va to'lov sxemasi; oylik hisob-kitobi — «Ish haqi» bosqichida), **Darslar** (shu hafta kunlar bo'yicha + to'liq jadvalga havola), **Fanlar** (fan → guruhlar, soat), **Sertifikatlar**. `Teacher.card_number` — oylik kartasi (shifrlangan, 16 raqam, formada). Asl tizimdan farqi: pasport, JSHSHIR, karta **niqoblangan** ko'rsatiladi, 221 test | ✅ tugadi (2026-10-02) |
| 3Z.10 | **Oyliklar → Oylik hisob-kitob** (`apps.payroll`: `domain/calc.py` — sof hisob, `selectors.month_payroll` — butun filial bir necha so'rovda). Asl tizimdagidek jadval: o'qituvchi, fanlar, darslar, o'quvchilar, asosiy oylik, ustamalar (toifa / sertifikat / til), jarimalar, S/R, Max (100%), Real; «Jami» qatori; 3 statistika (jami hisoblangan, shartnomalar, o'qituvchilar); oy tanlash (oldingi/keyingi), Excel. Darslar — jadval tarixidan (`lesson_occurrences`; o'qituvchi oy o'rtasida almashsa bo'linadi), o'quvchi ulushi — shu oy to'lov grafigi (`paid / full_amount`, max — `amount / full_amount`). O'qituvchi sahifasi: hisob tarkibi (Real/Max), guruhlar bo'yicha (ochiladigan — har o'quvchi: tarif, to'lashi kerak, to'lagan, ulush), **jarimalar** (`Penalty`: qo'shish, sabab bilan bekor qilish). «Sozlamalar» — toifa foizlari, sertifikat, til, sinf rahbarlik summasi. Hisob jonli (oy muhrlanmaydi). Keyingi: oyni yopish/muhrlash, avans va oylik to'lash (`SalaryPayment`), kechikkan to'lov farqini keyingi oyga o'tkazish, bayramlar; Excel qabul testi (namuna fayl kerak), 232 test | ✅ tugadi (2026-10-02) |
| 3Z.11 | **O'qituvchi maosh tafsilotlari** (asl tizimdagidek): «Oylik xulosa» (jami darslar, shartnomalar, o'quvchilar; Max/Real: asosiy, ustamalar, sinf rahbarlik, jarimalar, jami), profil, «Tezkor hisob» (Max, asosiy, ustamalar, S/R, Real, **Farq**), **«To'lov holati»** — hisoblangan, berilgan, qoldiq, holat (kutilmoqda / qisman / to'liq / ortiqcha), to'lovlar ro'yxati; **«Pul berish»** — `SalaryPayment` (avans / oylik, sana, naqd kassa yoki bank, izoh) → `finance.record_expense` «Ish haqi» xarajati (kassa chiqimi, naqd uchun ochiq kassa va yetarli qoldiq; kelgusi oy uchun berilmaydi). «Shartnomalar» ro'yxati: har guruh fani — sinf, fan, guruh kodi, sxema, Max (ustidan chizilgan) / Real (asosiy + shu qatorga tegishli ustama − ushlanma), ochilganda o'quvchilar; sinf rahbarligi qatorlari (N o'quvchi). O'qituvchi bo'yicha Excel. Ochiq: pul berishni kim qiladi (hozir Zavuch sahifasida; kassir bo'lsa tugma Reception'ga ko'chadi), to'lovni bekor qilish (storno), 234 test | ✅ tugadi (2026-10-02) |
| 3Z.12 | **Yotoqxona davomati** (Zavuch, asl tizimdagidek; `DormAttendance`: o'quvchi + kun + belgi B/Y/K/S, kim belgilagan; belgi yo'q — «belgilanmagan»). Sahifa: 6 statistika (jami o'quvchi, o'g'il, qiz, bugun bor — kechikkan bilan, bugun yo'q — sababli bilan, belgilanmagan), filtr (ism/kod, jinsi, xona, sinf, sanadan–sanagacha; sukut — oxirgi 20 kun, ko'pi 62), belgilar izohi, to'r: o'quvchi · xona × kunlar (shanba/yakshanba qizil, bugun ko'k) + B/Y/K/S jamilari, 30 tadan sahifa, Excel. **Katakni bosish** → kichik menyu (B/Y/K/S/O) → darhol saqlanadi, qator jamilari yangilanadi; yotoqxonada yashamagan kunlar — belgilanmaydi («·»), kelgusi kun — yo'q. Jadval bugungi kunga surilgan holda ochiladi. **«Kunlik belgilash»** (`/dorm/attendance/day/`): bir kun, xona filtri, har o'quvchiga B/Y/K/S/O, «Belgilanmaganlar — Bor», bitta «Saqlash». 239 test | ✅ tugadi (2026-10-02) |
| 4T.1 | **O'qituvchi → Bosh sahifa** (asl tizimdagidek; `ROLE_DASHBOARDS["teacher"]`, `academics.selectors.teacher_dashboard`): 4 statistika — bugungi darslar (keyingisi soati), o'quvchilarim (N guruh), haftalik darslar (Du–Sha, jadval tarixi bilan), guruhlarim; «Bugungi darslar» — vaqt, sinf · fan, xona · guruh kodi, holat **O'tdi / Hozir / Kutilmoqda** (qo'ng'iroq vaqti bo'yicha, «Hozir» ajratilgan); «Guruhlarim» — tanlov guruhlari kartalari (kod, fanlar, o'quvchi / sig'im, chiziq). Asl tizimdagidek «Guruhlarim» va «O'quvchilarim» faqat **tanlov guruhlari** bo'yicha (butun sinf guruhlari darslarda chiqadi). O'qituvchi kartasi yo'q foydalanuvchiga tushuntirish; **superadmin** (virtual o'qituvchi roli) — «Superadmin ko'rinishi»: o'qituvchini tanlaydi (`?teacher=`, sessiyada eslab qolinadi), panel o'sha o'qituvchi ma'lumotlari bilan. 244 test | ✅ tugadi (2026-10-02) |
| 4T.2 | **O'qituvchi → Mening jadvalim** (`/my/schedule/`, asl tizimdagidek): «Haftalik jadvalim — N soat/hafta», hafta varaqlash (Oldingi / Keyingi / Shu hafta, `?week=`), katta ekranda to'r (soat × Du–Sha, OBED qatori, bugungi ustun ajratilgan; katakda sinf, fan · xona, tanlov guruhi kodi), telefonda kunlar bo'yicha ro'yxat. Faqat ko'rish (jadvalni Zavuch tuzadi), jadval tarixi hisobga olinadi. Superadmin — «Superadmin ko'rinishi» (umumiy `_preview_bar.html`). `academics.selectors.week_day_lessons` (o'qituvchi kartasi bilan umumiy). 246 test | ✅ tugadi (2026-10-03) |
| 4T.3 | **O'qituvchi → Guruhlarim** (`/my/groups/`, asl tizimdagidek): tanlov guruhlari kartalari — kod, sinf · fan, daraja, to'lov sxemasi, Birlashma (guruhning hamma fanlari), **«Men o'qitaman»**, o'quvchi/sig'im, xona, «Boshqarish». Guruh sahifasi: sinfda / biriktirilgan / nomzodlar / bo'sh o'rin, ogohlantirish, **Guruh a'zolari** (qo'shilgan sana, chiqarish — `left_at`, tarixda qoladi, oylik uchun) va **O'quvchi biriktirish** (shu sinf nomzodlari, qidiruv, «+»). **Qoida (asl tizim): o'quvchi bir fan bo'yicha faqat bitta tanlov guruhida** — `selectors.subject_busy_students`, `group_service.add_members` rad etadi, nomzodlarda chiqmaydi (Zavuch sahifasida ham). Faqat o'z guruhlari (boshqasi — 404); sig'im to'lsa qo'shilmaydi; superadmin ko'rinishida ham boshqaradi (amal superadmin nomidan logga yoziladi); nomzod qatorining o'zi bosiladi. 250 test | ✅ tugadi (2026-10-03) |
| 4T.4 | **O'qituvchi → Sinf rahbarlik** (`/my/homeroom/`, asl tizimdagidek; `ClassAttendance`: sinf + o'quvchi + kun + belgi ✓/✗/K/S + izoh, kim kiritgan). Ro'yxat: rahbar bo'lgan sinflar, o'quvchilar soni, bugungi holat (Kiritilmagan / Qisman / Kiritilgan). Sinf sahifasi — 3 bo'lim: **Kunlik davomat** (sana — bugungacha, katakni bosish: bo'sh → ✓ → ✗ → K → S, «Hammasi keldi», ota-ona — asosiy vasiy ismi · telefoni, izoh/sabab, bitta «Saqlash»; izoh bor-u belgi yo'q — rad etiladi, kelgusi kun — yo'q), **Haftalik jadval** (sinf jadvali, hafta varaqlash), **Oylik statistika** (o'quvchi × kun, ✓/✗/K/S jamilari, kelish % = (keldi+kechikdi)/belgilangan) + Excel. Faqat o'z sinfi (boshqasi — 404), superadmin ko'rinishi. Demo: 4-B → Karimov Aziz. 253 test | ✅ tugadi (2026-10-03) |
| 4T.5 | **O'qituvchi → «Oylik qanday hisoblanadi»** (`/my/salary-guide/`, asl tizim mazmuni, Apple uslubida): kirish kartasi, yopishqoq bo'limlar menyusi; **simulyator** (20 o'quvchi: bosib to'ladi/to'lamadi, tayyor holatlar 100% / 80% / 1 ta to'lamadi → foiz va chiziq), **tarkibi** (aylanadigan 3 karta — asosiy, ustamalar, sinf rahbarlik; foizlar va S/R stavkasi `PayrollSettings`dan jonli), **oy davomida** (4 qadam, «Boshlash» / oldingi / keyingi), **amaliy misol** (namuna ustoz — haqiqiy emas; Avans / Oylik / Jami tablari), **kechikib to'lash** (javobni ochish, sentabr → oktabr), **boshqa holatlar** + kafolat, **kalkulyator** (to'liq oylik, to'lov % va avans % slayderlari; avans va oy oxiri mingga pastga, qoldiq keyingi oyga — asl misoldagi 18 197 250 / 5 459 000 / 12 738 000 / 250 bilan mos), **savollar** (qidiruv). Matnlar tizimimizning haqiqiy ishlashiga moslangan (jonli qayta hisob, «Qoldiq»). 254 test | ✅ tugadi (2026-10-03) |
| 4T.6 | **O'qituvchi → Oyligim («Olingan oyliklar»)** (`/payroll/my/`, asl tizimdagidek): «Jami olingan oyliklar» (summa, to'lovlar soni), oylar bo'yicha guruhlar (oy jami; har to'lov — summa, Avans/Oylik, sana · naqd/bank · filial · izoh) — `SalaryPayment` (Zavuch «Pul berish»da kiritadi). Qo'shimcha: **shu oy hisobi** — hisoblangan (to'lovlar bo'yicha), 100% bo'lsa, berilgan, qoldiq, holat. O'qituvchi paneli umumiy konteksti — `academics.panel.teacher_ctx` (superadmin ko'rinishi ham). 255 test | ✅ tugadi (2026-10-03) |
| 5D | **Direktor paneli** (`Role.DIRECTOR`, `apps.director` — o'z modeli yo'q, boshqa ilovalardan jamlaydi). **Bosh sahifa**: o'quvchilar (+keldi/−ketdi), shu oy tushum (o'tgan oyga %), muddati o'tgan qarz (o'qish+yotoqxona), sof natija; o'qituvchilar, oylik fondi (real/100%/berilgan), bugungi sinf davomati, yotoqxona bandligi; kirim/chiqim 6 oy (bitta shkala), pul qoldiqlari (naqd/bank/terminal), o'qish to'lovi holati, o'quvchilar trendi, byudjet. **Moliyaviy hisobot** (oy: kirim turlari, chiqim kategoriyalari — oyliklar ham, sof natija, 12 oylik jadval). **Davomat hisoboti** (kun: sinflar kesimida ✓/K/✗/S, kiritilmagan sinflar, yotoqxona). **Xodimlar va kirish** (filial xodimlari, rollari; Reception/Zavuch/O'qituvchi rolini yoqish-o'chirish — o'zini va direktor rolini emas; log). Ko'rish: o'quvchilar, ota-onalar, shartnomalar, o'qituvchilar, moliya ro'yxatlari, kassa, sinflar, dars jadvali (sudrash o'chiq), oylik (to'lov/jarima yo'q), yotoqxona (davomat belgilash o'chiq) — `*_VIEW_ROLES`. Interfeys: `[data-role=director]` da `[data-write]` va `main form[method=post]:not([data-readonly-ok])` yashirin, holat formalari o'rniga `.ro-only` nusxa. Demo: Abdullayev Sardor (998900000005). 288 test | ✅ tugadi (2026-10-03) |
| 6A | **O'ziga xoslik: tozalash** (foydalanuvchi qarori, 2026-10-03 — loyiha boshqalarga berilishi mumkin, asl tizimdan nusxa bilinmasin). Sukut **shartnoma shabloni** — o'zimiz yozgan umumiy namuna (`contracts/default_template.txt`; asl maktab matni olib tashlandi, faylning git tarixi yo'q; mavjud bazadagi shablonga tegilmadi — 66 ta imzolangan demo shartnoma muhrlanmagan, matni o'zgarmasin). **«Ish haqi qoidalari»** sahifasi qayta yozildi (asl tuzilish va matnlar olib tashlandi): bosiladigan formula, o'qituvchining shu oydagi shaxsiy hisobi (haqiqiy / reja), «bitta o'quvchi sizga qancha keltiradi» kalkulyatori (darsbay / belgilangan, chegirma, to'lov %), avans kalkulyatori, oy taqvimi, savol-javob. **Atamalar**: «Oylik» → «Ish haqi» (Ish haqi hisobi, Ish haqim, Ish haqi qoidalari, Ish haqi sozlamalari), «Max / Real» → «Reja (100%) / Hisoblangan (Haqiqiy)», «Tezkor hisob» → «Qisqacha», «Oylik xulosa» → «Hisob tarkibi», «To'lov holati» → «Berilgan pul», «Jarimalar» → «Ushlanma», Reception menyusi «Kirim» → «Moliya». 308 test | ✅ tugadi (2026-10-03) |
| 7 | **Deploy (MVP sinov, Contabo)** — `docs/DEPLOY.md`. `deploy/make-env.sh` (`.env.prod` — barcha maxfiy kalitlar tasodifiy, faqat domen/IP so'raladi, ustiga yozmaydi), `HTTPS=false` — domensiz IP sinov rejimi (aks holda prod qat'iy HTTPS), nginx ikki shablon (`deploy/nginx/http|https`, `${DOMAIN}` envsubst, `NGINX_MODE`), certbot (webroot, bir martalik + cron yangilash), `deploy/entrypoint.sh` (avtomatik migrate). Lokal Docker'da to'liq sinovdan topilib tuzatildi (avvaldan bor xatolar): root'siz konteynerda `uv run` kesh papkasi yo'qligidan **ilova umuman ishga tushmasdi** (endi `.venv` PATH'da, ish vaqtida uv yo'q); nginx `keepalive_timeout` takrori — **nginx ishga tushmasdi**; `seed_demo` toza bazada yiqilardi (o'quvchi holatlari, naqd to'lov sanasi) — test qo'shildi. Sinov: build → migrate → healthz → seed_demo → login (CSRF/cookie) → sahifalar 200, HTTPS shabloni `nginx -t`. Cron: oylik grafiklar, kodlarni tozalash, kunlik `pg_dump`, sertifikat yangilash. 309 test | ✅ tayyor (2026-10-03) |
| 6B | **Nazorat va qulayliklar**: audit jurnali (kim, qachon, nima — direktorga), oyni yopish va ish haqini muhrlash (o'tgan oylar sozlama o'zgarsa ham o'zgarmaydi), bildirishnomalar markazi, global qidiruv (⌘K) | ⏳ navbatda |
| 6C | **Ota-ona portali + Telegram**: farzandning davomati, qarzi, to'lovlari, jadvali; to'lov muddati va qarz eslatmalari | ⏳ |
| 6D | **Elektron jurnal**: baho va uy vazifasi, o'zlashtirish hisobotlari (sinf rahbari, direktor, ota-ona) | ⏳ |
| 6E | **Analitika va prognoz** (kassa prognozi, ketish xavfi, direktorga haftalik Telegram hisobot) va **ruscha interfeys** | ⏳ |
| — | **Ochiq savol:** imzolangan shartnomada tarif/chegirmani o'zgartirish (asl tizimda: "yangi tarif biriktiriladi, eski yopiladi"). Oyma-oy grafik tufayli osonlashdi: yaratilmagan oylar yangi tarif bilan chiqadi; yaratilgan, lekin to'lanmagan oylar bilan nima qilish kelishilmagan | |
| 2R.2b | Moliya ro'yxat sahifalari: ~~To'lovlar~~ ✅, ~~Tranzaksiyalar~~ ✅, ~~Bank hisobi~~ ✅, ~~To'lov grafiklari~~ ✅, ~~Qarzdorlar~~ ✅ — **2R.2b to'liq tugadi**. Kvitansiya — ✅ tayyor | ✅ tugadi (2026-09-29) |
| UI | **Apple uslubidagi redizayn** — `app.css` to'liq qayta yozildi (barcha klasslar saqlangan), tab bar, sheet panellar, 174 test | ✅ tugadi (2026-09-29) |
| 2R.3 | Reception: yotoqxona — **`apps.dorm`**: `DormRoom` (o'g'il/qiz/aralash, o'rinlar, oylik to'lov), `DormStay` (bitta faol qayd, tarix o'chirilmaydi), joylashtirish qoidalari (faol, shu filial, jins mos, bo'sh o'rin — `select_for_update`); menyu: Boshqaruv paneli ✅ (bandlik, filiallar bo'yicha, hozir yashayotganlar: filtr, Excel, "Yana yuklash"), **Xonalar** ✅ (xona turi 2/4/6/8 o'rinli, qavat, holat faol/nofaol/ta'mirda — `is_active` ma'lumot ko'chirish bilan almashtirildi; statistika, "Filtr qo'shish": holat/jinsi/xona turi, band/sig'im, Excel; xona sahifasi: yashayotganlar, joylashtirish — faqat mos o'quvchilar, chiqarish, tarix). **To'lov grafiklari** ✅: `Invoice(category=dorm, dorm_stay)`, `DormStay.monthly_fee` (xona narxidan kami — chegirma); joylashtirilganda joriy oygacha yaratiladi (kirgan oy proratsiya), cron `generate_monthly_invoices` yotoqxonani ham qo'shadi, chiqqanda chiqqan oy kunlar bo'yicha + keyingi to'lanmagan oylar bekor (oldindan to'langan saqlanadi), o'qishdan chiqqanda qayd avtomatik yopiladi; sahifa: 6 statistika, filtr (o'quv yili — oylar oralig'i, oy, holat), Excel; to'lov qabul qilish `?category=dorm`. **Qarzdorlar** ✅: Kirim → Qarzdorlar bilan umumiy selector/shablon/yon panel (`InvoiceFilters.category`, `?category=dorm`), faqat yotoqxona oylari (o'qish qarzi aralashmaydi), oxirgi to'lov — shu turdagi, filtr (o'quv yili, oy, holat: kutilmoqda/qisman/muddati o'tgan), Excel; ℹ️ panelda "Oxirgi to'lov" satri. **Ochiq savol:** asl tizimdagi "To'lov rejalari" (6–11 oylik oldindan to'lovga chegirma) — narxlar kelishilmagan, qilinmadi. Mulkdor to'lovlari — ⏳; xona qo'shish/tahrirlash hozircha admin orqali; 170 test | ⏳ davom etmoqda |
| 3Z | **Zavuch** — sinflar va guruhlar boshqaruvi, o'qituvchilar (HR), dars jadvali (ziddiyat tekshiruvi, chop etish), yotoqxona davomati, oylik hisob-kitob jadvali | |
| 4T | **O'qituvchi** — bosh sahifa, mening jadvalim, guruhlarim, sinf rahbarlik, oylik dvigateli (Excel qabul testi), olingan oyliklar, "oylik qanday hisoblanadi" | |
| 9 | Sayqal: Excel eksport, ⌘K qidiruv, ruscha tarjima, Direktor/Superadmin | |
| 10 | O'quvchilar uchun test paneli (o'qituvchi test yaratadi, o'quvchi ishlaydi) + bitta IP ortidagi yuklama uchun limitlarni qayta sozlash | |
| 11 | Deploy (Contabo): Docker Compose, Cloudflare, SSL, shifrlangan backup → Google Drive, monitoring | |

## 6. Dizayn tizimi

**2026-09-29 dan: Apple Human Interface Guidelines uslubi** (foydalanuvchi qarori; oldingi NiceSchool palitrasi
va Onest/Raleway shriftlari bekor qilindi). **To'liq qo'llanma — `docs/DESIGN.md`** (tokenlar, komponentlar,
qilinmaydiganlar, yangi sahifa tekshiruv ro'yxati). Barcha yangi UI shu qo'llanma bo'yicha quriladi.

- **Bitta dizayn tili** barcha rollar uchun. Tamoyillar: aniqlik (kontent birinchi), bo'ysunish (navigatsiya shaffof
  "material"da, kontent qattiq sirtda), chuqurlik (qatlamlar soya/blur bilan, chegara chiziqlari deyarli yo'q).
- **Shrift:** tizim shrifti — Apple qurilmalarida SF Pro / katta raqamlar uchun SF Pro Rounded (`ui-rounded`),
  qolganlarida **Inter** (Google Fonts, kirill bor). SF Pro va SF Symbols litsenziyasi veb-saytga joylashtirishga
  ruxsat bermaydi — fayl sifatida yuklanmaydi. Ikonlar o'zimizniki (SF Symbols'ga o'xshash ingichka chiziq).
- **Ranglar:** Apple tizim ranglari (`--c-blue/green/orange/red/purple/indigo/teal/pink`). Kunduzi — matn sifatida
  o'qiladigan to'yinganlik, tunda — Apple'ning tungi variantlari. Fon `#F2F2F7`, sirt `#FFF`; tungi rejim `#000` /
  `#1C1C1E` / `#2C2C2E` (neytral kulrang). Kulrang to'ldirish — `--fill`, `--fill-2`, `--fill-strong`.
- **Urg'u:** hamma rolda systemBlue (`--accent`). **Rol belgisi** `--role`: o'qituvchi — yashil, zavuch — indigo,
  reception — to'q sariq; faqat kichik nuqta (sidebar, rol tugmasi) sifatida.
- **Komponentlar:** kapsula tugmalar (filled / tinted `.btn-outline` / gray `.btn-secondary` / plain `.btn-ghost`),
  Segmented Control (`.segmented`, `.radio-row`, `.tabs`), iOS switch (`.check input[type=checkbox]`), dumaloq ✓
  (`.check-item`), select'da ↕ belgisi, Apple Alert uslubidagi tasdiqlash oynasi, macOS menyu materiali (dropdown).
- **Qobiq:** suzuvchi shaffof sidebar (tanlangan band — to'liq ko'k, matn oq), shaffof yuqori panel, katta sarlavha
  (Large Title). **Telefonda (≤768px) pastki suzuvchi tab bar** — rolga qarab 4 ta bo'lim + "Menyu"
  (`navigation.TAB_BAR`, `build_tabbar`). Yon panellar: kompyuterda chetdan ajralgan suzuvchi varaq, telefonda
  **pastdan chiquvchi sheet** (tutqich bilan). Xabarlar — o'ng yuqorida bildirishnoma, 6 soniyada yo'qoladi.
- **Burchaklar konsentrik:** 6 / 10 / 14 / 20 / 26 px (`--radius-xs … --radius-xl`). Harakat: `--ease` (spring'ga yaqin).
- Statistika kartalari: yumshoq (tint) dumaloq ikon + SF Rounded raqam. To'liq rangli bloklar ishlatilmaydi.
- Jadval amallari: dumaloq ikon tugmalar `.icon-btn.tone-*`. Xavfli amallar — `<form data-confirm="…">`.
- Tokenlar: `static/css/app.css` boshida. Yangi rang to'g'ridan-to'g'ri yozilmaydi — faqat token.
- Maktab logotipi rangi (`SchoolSettings.brand_color` → `--brand`) faqat brend belgisida (ilova ikonkasi kabi gradient).
- Dark mode: tizim sozlamasi + qo'lda almashtirish (`localStorage.theme`). `prefers-reduced-motion` hurmat qilinadi.
- Ikonlar: `templates/partials/icons.html` SVG sprite, `{% include "partials/icon.html" with name="…" %}`.
- Chop etish sahifalari (shartnoma, kvitansiya) dizayn tokenlaridan mustaqil — oq qog'oz, qora matn.
- Keyin qo'shiladi: ⌘K global qidiruv, skeleton loaderlar.

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
- **Cron (prod, kuniga 1 marta):** `manage.py generate_monthly_invoices` (yangi oy grafigi) va `manage.py purge_expired_codes`. Dev'da kerak bo'lsa qo'lda ishga tushiring.
