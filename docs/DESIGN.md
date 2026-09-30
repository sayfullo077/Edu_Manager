# Edu Manager — dizayn qo'llanmasi (Apple HIG uslubi)

> **Majburiy qoida.** Har bir yangi sahifa, komponent yoki o'zgarish **shu qo'llanma bo'yicha** quriladi.
> Yangi sahifa qurishdan oldin shu faylni o'qing. Qo'llanmada yo'q yangi komponent kerak bo'lsa —
> avval shu uslubda `static/css/app.css` ga qo'shing, keyin **shu faylga ham yozing**.
>
> Qaror: 2026-09-29, foydalanuvchi. Manba: Apple Human Interface Guidelines (iOS 26 / macOS Tahoe uslubi).
> Oldingi NiceSchool palitrasi, Onest/Raleway shriftlari va rolga qarab o'zgaradigan urg'u **bekor qilingan**.

---

## 1. Tamoyillar

1. **Aniqlik (clarity)** — kontent birinchi. Bezak, ramka va chiziqlar minimal; ierarxiya shrift og'irligi,
   o'lcham va bo'shliq bilan beriladi.
2. **Bo'ysunish (deference)** — navigatsiya (sidebar, yuqori panel, tab bar, menyular) shaffof "material"da
   (blur); kontent (kartalar, jadvallar, formalar) — qattiq, shaffof bo'lmagan sirtda. **Kontentga blur berilmaydi.**
3. **Chuqurlik (depth)** — qatlamlar soya va blur bilan ajraladi: fon → karta → suzuvchi panel → dialog.
4. **Izchillik** — bir xil vazifa hamma joyda bir xil komponent bilan. Yangi uslub o'ylab topilmaydi.
5. **Hamma uchun** — kontrast ≥ 4.5 (matn), tegish maydoni ≥ 36–44px, `prefers-reduced-motion` hurmat qilinadi,
   tungi rejim har doim ishlaydi.

## 2. Asosiy texnik qoidalar

- Ranglar, radiuslar, soyalar **faqat tokenlar** orqali (`var(--…)`). Komponentda hex/rgb rang yozilmaydi.
  Istisno: chop etish sahifalari (`.sheet`) — oq qog'oz, qora matn.
- Inline `style=""` yo'q (CSP). Kenglik/foiz kerak bo'lsa — SVG atributi yoki tayyor klass.
- Ikonlar faqat `{% include "partials/icon.html" with name="…" class="sm" %}` (sprite: `partials/icons.html`).
- Yangi CSS `static/css/app.css` ning tegishli bo'limiga yoziladi (fayl oxiriga tartibsiz qo'shilmaydi).
  Moslashuvchan qoidalar — fayl oxiridagi umumiy `@media` bloklariga.
- Har bir yangi sahifa **yorug' + tungi rejimda** va **kompyuter (≥1024) + telefon (375px)** kengligida
  brauzerda tekshiriladi.

## 3. Tokenlar (`static/css/app.css` boshida)

### Shrift
| Token | Qiymat | Qayerda |
|---|---|---|
| `--font` | `-apple-system, "SF Pro Text", "Inter", …` | Asosiy matn |
| `--font-heading` | `-apple-system, "SF Pro Display", "Inter", …` | Sarlavhalar |
| `--font-rounded` | `ui-rounded, "SF Pro Rounded", …` | **Katta raqamlar/summalar** (statistika, balans, jami) |
| `--font-mono` | `ui-monospace, "SF Mono", …` | Hujjat raqamlari (`.doc-code`) |

- SF Pro / SF Symbols **fayl sifatida yuklanmaydi** (Apple litsenziyasi veb-saytga ruxsat bermaydi) — faqat
  qurilmaning o'zidan. Apple bo'lmagan qurilmalarda Inter (Google Fonts, kirill bor).
- O'lchamlar: body 15px; Large Title (`.page-head h1`) 32px/700; bo'lim sarlavhasi 22px; karta sarlavhasi 17px;
  izoh/label 12.5–13.5px. Sarlavhalarda manfiy harf oralig'i (`-0.018em … -0.03em`).
- Raqamlar doim `tabular-nums` (`.num` yoki jadval katagi).

### Ranglar
| Token | Kunduzi | Tunda | Ma'nosi |
|---|---|---|---|
| `--bg` | `#F2F2F7` | `#000000` | Sahifa foni (grouped background) |
| `--surface` | `#FFFFFF` | `#1C1C1E` | Karta, panel |
| `--surface-2 / -3` | `#F5F5F7 / #E8E8ED` | `#2C2C2E / #3A3A3C` | Ichki sirtlar |
| `--fill`, `--fill-2`, `--fill-strong` | kulrang 12% / 7% / 20% | 24% / 14% / 36% | Kulrang tugma, trek, hover |
| `--heading`, `--text`, `--text-2`, `--muted`, `--faint` | `#1D1D1F … #AEAEB2` | `#F5F5F7 … #636366` | Matn darajalari |
| `--border`, `--border-strong` | `#E5E5EA`, `#D1D1D6` | `#38383A`, `#48484A` | Ajratuvchi chiziq, input chegarasi |
| `--accent` | systemBlue `#007AFF` | `#0A84FF` | **Yagona urg'u rangi** (hamma rolda) |
| `--success / --warning / --danger / --info` | `#248A3D / #C9620A / #D92D20 / #007AFF` | `#30D158 / #FF9F0A / #FF453A / #0A84FF` | Holatlar |
| `--*-soft` | shu rang 11–12% | — | Tint fon (badge, alert, ikon bloki) |
| `--success-fill`, `--danger-fill` | to'q yashil/qizil | — | Oq matnli to'liq tugmalar |
| `--c-blue/green/orange/red/purple/indigo/teal/pink` | Apple tizim ranglari | tungi variantlar | Avatar, grafik, rol |
| `--role` | O'qituvchi — yashil, Zavuch — indigo, Reception — to'q sariq | | **Faqat kichik nuqta** (sidebar, rol tugmasi) |
| `--brand` | `SchoolSettings.brand_color` | | Faqat maktab brend belgisi (`.brand-mark`) |
| `--glass`, `--glass-strong`, `--blur` | | | Navigatsiya materiali |

### Shakl va harakat
- Radiuslar (konsentrik): `--radius-xs` 6 · `--radius-sm` 10 (input) · `--radius` 14 (ichki blok) ·
  `--radius-lg` 20 (karta) · `--radius-xl` 26 (panel, sheet) · `--radius-pill` (tugma, badge, chip).
  Ichki element radiusi tashqisidan kichik bo'ladi.
- Soyalar: `--shadow` (karta, juda yumshoq), `--shadow-float` (hover, tab bar), `--shadow-lg` (panel, dialog).
  Tungi rejimda soya o'rniga yupqa yorug' chiziq.
- Harakat: `--ease` (spring'ga yaqin, 0.3–0.45s), `--ease-out` (paydo bo'lish). Bosilganda `scale(0.97)`.

## 4. Sahifa qolipi

```django
{% extends "layouts/app.html" %}
{% load ui %}
{% block title %}Sahifa nomi{% endblock %}
{% block content %}
<div class="page-head">
  <div>
    <a class="back-link" href="…">{% include "partials/icon.html" with name="arrow-left" class="sm" %} Orqaga</a>  {# ixtiyoriy #}
    <h1>Sahifa nomi</h1>
    <p class="sub">Qisqa izoh · N ta</p>
  </div>
  <div class="page-actions"><a class="btn btn-primary" href="…">{% include "partials/icon.html" with name="plus" class="sm" %} Qo'shish</a></div>
</div>
… statistika → filtr → karta (jadval) …
{% endblock %}
```

- Bitta sahifada **bitta** `btn-primary` (asosiy amal). Qolganlari — tinted/gray.
- Qobiq (`layouts/app.html`): suzuvchi shaffof sidebar (tanlangan band to'liq ko'k, matn oq), shaffof yuqori panel,
  telefonda pastki **tab bar** (≤768px). Yangi bo'lim menyuga `apps/accounts/navigation.py` → `NAVIGATION` orqali;
  telefonda tez-tez kerak bo'lsa `TAB_BAR` ga (rolga 4 ta, 5-chisi "Menyu").

## 5. Komponentlar

### Tugmalar (kapsula)
| Klass | Apple uslubi | Qachon |
|---|---|---|
| `.btn-primary` | Filled (ko'k) | Sahifaning asosiy amali |
| `.btn-success` | Filled (yashil) | To'lov/tasdiqlash |
| `.btn-danger` | Filled (qizil) | Tasdiqlash oynasidagi xavfli amal |
| `.btn-outline` | Tinted (ko'k och fon) | Ikkinchi darajali amal |
| `.btn-excel`, `.btn-danger-soft`, `.btn-warning-soft` | Tinted | Eksport, o'chirish, ogohlantirish |
| `.btn-secondary` | Gray | Bekor qilish, filtr |
| `.btn-ghost` | Plain | Ikonli yordamchi tugmalar |

O'lcham: `.btn-sm` (32), sukut (40), `.btn-lg` (50); `.btn-icon` — kvadrat; `.btn-block` — to'liq kenglik.
Yonma-yon juft (ma'lumot + to'lov): `<div class="split-btn">…</div>`.
Jadval qatori amallari: `.icon-btn.tone-info|success|warning|danger` (dumaloq, tint). Ustun sarlavhasi doim
ko'rinadi: `<th class="actions">Amallar</th>`; har bir ikon tugmada `title` va `aria-label` bo'ladi.

### Formalar
- Maydon: `{% include "partials/field.html" with field=form.x %}` — label, xato, yordam matni avtomatik.
- `.input` 44px, radius 10, fokusda ko'k halqa. `select.input` — Apple ↕ belgisi avtomatik.
- Boolean → **iOS switch** (`.check` ichidagi checkbox avtomatik switch bo'ladi).
- Radio tanlov (2–4 variant) → **Segmented Control** (`.radio-row`, `field.html` avtomatik beradi).
- Ko'p tanlov ro'yxati → `.check-item` (dumaloq ✓); filtrda `partials/multiselect.html`.
- Prefiks: `.input-group` + `.addon` (`+998`, `so'm` → `.input-group.suffix`).
- Katta formalar — yig'iladigan bo'limlar `.card.form-fold`, maydonlar `.form-grid.cols-2|3|4`.
- Xabar bloki: `.alert.alert-info|success|error`.

### Ko'rinishni almashtirish
- Sahifa ichidagi bo'limlar/ko'rinishlar → Segmented Control: `<nav class="segmented">` yoki karta ichida
  `<nav class="tabs">` (`aria-current="page"` tanlanganiga). Pastki chiziqli "tab"lar ishlatilmaydi.

### Statistika kartalari
```django
<div class="grid grid-3x2 stats-row">   {# 6 ta → grid-3x2; 5 ta → grid-5; 4 ta → grid-4 #}
  <div class="card stat">
    <div class="top"><span class="label">To'langan</span>
      <span class="ico tone-success">{% include "partials/icon.html" with name="check" class="sm" %}</span></div>
    <div class="value money-sm text-success">{{ x|money }} <span class="unit">so'm</span></div>
  </div>
</div>
```
- Ikon bloki — **yumshoq tint doira** (`.ico.tone-*`). To'liq rangli bloklar ishlatilmaydi.
- Raqam — `--font-rounded`. Birlik (`so'm`, `nafar`) — `.unit`.
- Kartalar soni to'rga teng bo'linsin (yolg'iz qolgan keng karta bo'lmasin).

### Ro'yxat sahifasi (filtr + jadval)
- Filtr: `{% include "partials/filter_bar.html" with placeholder="…" %}` (forma: `FILTERS`, `active_filters()`,
  `to_filters()`; view'da `common.forms.filter_menu`). Natija chiplari: `.chip-row.result-chips`.
  Ixtiyoriy tugmalar: `export_url` (Excel), `print_url` ("Ro'yxat" — chop etish sahifasi, joriy filtr bilan).
- Chop etish ro'yxati: `print-page` + `.sheet` + `table.sheet-table.print-list` (guruh sarlavhasi `h2`), qarang
  `people/student_print.html`.
- Jadval: `<div class="card"><div class="table-wrap"><table class="table table-dense">…` +
  `{% include "partials/pagination.html" %}`. Sarlavhalar oddiy yozuvda (KATTA HARF emas).
- Shaxs katagi: `<a class="person"><span class="avatar t{{ code|tone }}">…</span><span><b>Ism</b></span></a>`.
- Holat: `.badge.badge-success|warning|danger|info|muted|pink` (kapsula, tint). Jinsi: o'g'il — `badge-info`,
  qiz — `badge-pink`.
- Pul ustunlari `text-right num`; qarz `text-danger`, to'langan `text-success`.
- Tor ekranda yashirish: `.hide-xl` (≤1320), `.hide-lg` (≤1180), `.hide-sm` (≤1024), `.hide-xs` (≤700).
- Bo'sh holat: `.empty` (dumaloq kulrang ikon + sarlavha + izoh).

### Batafsil ma'lumot
- Kalit–qiymat: `.kv` yoki `.kv-plain`; ro'yxat: `.list-plain`, `.entity-list` (iOS inset grouped).
- Kichik yig'indilar: `.sum-grid` / `.mini-grid` / `.drawer-stats` (kulrang tint bloklar, chegarasiz).

### Yon panel va dialoglar
- Tez amal (to'lov, ma'lumot): `<dialog class="side-panel" id="side-panel">` + tugmada `data-panel-url` —
  kompyuterda chetdan ajralgan suzuvchi varaq, **telefonda pastdan chiquvchi sheet** (avtomatik).
  Ichida: `header.drawer-head` → `.drawer-body` → pastda `.drawer-actions` (asosiy + "Bekor qilish").
- Forma oynasi: `<dialog class="modal">` (`.modal-head/.modal-body/.modal-foot`), ochish `data-open-dialog`.
- Xavfli amal: `<form data-confirm="Savol?" data-confirm-ok="Ha">` → Apple Alert uslubidagi umumiy oyna.
- Xabarlar: Django `messages` — o'ng yuqorida bildirishnoma, 6 s da yo'qoladi (telefonda to'liq kenglik).

### Katta formalar (qabul)
- Bo'limlar — `.card.form-fold`, sarlavhada holat belgisi `.badge.badge-muted` ("majburiy", "kamida bittasi").
- Yoqib-o'chiriladigan blok (Ota / Ona / Olib keluvchi): `.guardian-box.slot` + sarlavhada switch
  (`.check.slot-head` > `input[data-slot-toggle]`) + `[data-slot-body]`. O'chiq blok — faqat sarlavha, fon yo'q;
  server o'chiq blok formasini bog'lamaydi (tekshirilmaydi, saqlanmaydi).
- Bog'liq tanlagichlar: viloyat → tuman (`[data-address]`, `district-map` JSON), mahalla — `<datalist>`
  (serverdan, yangi nom yozilsa saqlanganda ma'lumotnomaga tushadi). Sinf → grade va tarif (`data-grade`,
  `data-tariff`), jonli hisob — `[data-fee-calc]` + `.fee-summary` (`data-discount-output`, `data-fee-output`).

### Grafiklar
- Serverda SVG (`apps/common/charts.py`), ranglar `--c-*` / `.seg-success|info|amber|danger|pink`; chiziqlar
  dumaloq uchli, to'r chiziqlari yupqa; tooltip `.chart-tip` (material).
- Tayyor qismlar: o'quvchilar trendi — `{% include "partials/trend_chart.html" %}` (kontekst: `trend`,
  `trend_chart`); donut — `common.charts.donut`; gorizontal ustunli ro'yxat — `ul.class-bars` + `{% bar %}`.
- Dashboard qolipi: `grid-5` kartalar → `grid-charts` (trend + donut) → `grid-2` (ro'yxatlar). Har rol o'z
  ma'lumotini ko'radi: Zavuch — faqat ta'lim (moliya yo'q), Reception — moliya.

## 6. Moslashuvchanlik

| Kenglik | Nima o'zgaradi |
|---|---|
| ≤1024 | Sidebar — chapdan chiquvchi suzuvchi panel; yuqorida maktab belgisi; qidiruv yashirinadi |
| ≤900 | 2 ustunli to'rlar 1 ustunga, statistika 2 ustunga |
| ≤768 | **Pastki tab bar**, kontent pastidan joy qoldiriladi |
| ≤640 | Yon panellar → pastki sheet; formalar 1 ustun |
| ≤600 | Statistika 1 ustun |

## 7. Qilinmaydi ❌

- Hex rang, inline style, tashqi UI kutubxona (Bootstrap va h.k.), yangi shrift.
- Rolga qarab butun interfeys rangini o'zgartirish (rol — faqat `--role` nuqtasi).
- KATTA HARFLI sarlavhalar va yorliqlar (Apple oddiy yozuv ishlatadi).
- Qalin ramkalar, rangli chap chiziqlar, to'liq rangli ikon bloklari yonma-yon.
- Kontent kartalariga blur/shaffoflik.
- Bir sahifada bir nechta `btn-primary`.

## 8. Yangi sahifa uchun tekshiruv ro'yxati ✅

1. Qolip: `page-head` (Large Title + `.sub`), bitta asosiy amal.
2. Faqat mavjud komponentlar va tokenlar; yangi komponent bo'lsa — `app.css` + shu faylga yozildi.
3. Ikonlar sprite'dan; raqamlar `num`/rounded; pul `|money` + `so'm`.
4. Yorug' va tungi rejim tekshirildi.
5. Kompyuter va telefon (375px) tekshirildi: tab bar kontentni yopmaydi, jadval sig'adi yoki ustunlar yashirinadi.
6. Menyu (`NAVIGATION`) va kerak bo'lsa `TAB_BAR` yangilandi.
