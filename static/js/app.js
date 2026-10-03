(() => {
  const root = document.documentElement;

  // --- Tema (yorug'/qorong'i) ---
  const storedTheme = () => { try { return localStorage.getItem("theme"); } catch { return null; } };
  const isDark = () => root.dataset.theme === "dark" ||
    (!root.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const syncThemeIcons = () => document.querySelectorAll("[data-theme-toggle] use")
    .forEach((u) => u.setAttribute("href", isDark() ? "#i-sun" : "#i-moon"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-theme-toggle]")) return;
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
    syncThemeIcons();
  });
  if (storedTheme()) root.dataset.theme = storedTheme();
  syncThemeIcons();

  // --- Yig'iladigan menyu (akkordeon): bittasi ochilsa, boshqalari yopiladi; tanlov eslab qolinadi ---
  const navGroups = [...document.querySelectorAll("[data-nav-group]")];
  if (navGroups.length) {
    const KEY = "nav:open";
    let saved = null;
    try { saved = localStorage.getItem(KEY); } catch {}
    // Faol sahifa guruhi har doim ochiq; aks holda oxirgi ochilgan guruh.
    if (!navGroups.some((g) => g.hasAttribute("data-active")) && saved) {
      navGroups.forEach((g) => { g.open = g.dataset.navGroup === saved; });
    }
    navGroups.forEach((g) => g.addEventListener("toggle", () => {
      if (!g.open) return;
      navGroups.forEach((other) => { if (other !== g) other.open = false; });
      try { localStorage.setItem(KEY, g.dataset.navGroup); } catch {}
    }));
  }

  // --- Mobil sidebar ---
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-nav-toggle]")) document.body.classList.toggle("nav-open");
    else if (e.target.closest(".backdrop")) document.body.classList.remove("nav-open");
  });

  // --- Dropdown: tashqariga bosilganda yopish ---
  document.addEventListener("click", (e) => {
    document.querySelectorAll("details.dropdown[open]").forEach((d) => {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll("details.dropdown[open]").forEach((d) => d.removeAttribute("open"));
  });

  // --- Telefon maskasi: 90 123 45 67 ---
  document.querySelectorAll("[data-phone-mask]").forEach((input) => {
    const fmt = (v) => {
      let d = v.replace(/\D/g, "");
      if (d.startsWith("998") && d.length > 9) d = d.slice(3);
      d = d.slice(0, 9);
      return [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean).join(" ");
    };
    input.value = fmt(input.value);
    input.addEventListener("input", () => { input.value = fmt(input.value); });
  });

  // --- Parolni ko'rsatish ---
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-toggle-password]");
    if (!btn) return;
    const input = btn.parentElement.querySelector("input");
    input.type = input.type === "password" ? "text" : "password";
    btn.setAttribute("aria-pressed", input.type === "text");
  });

  // --- OTP kataklari ---
  document.querySelectorAll("[data-otp]").forEach((wrap) => {
    const hidden = wrap.parentElement.querySelector("input[type=hidden][name=code]");
    const cells = [...wrap.querySelectorAll("input")];
    const form = wrap.closest("form");
    const sync = () => {
      hidden.value = cells.map((c) => c.value).join("");
      cells.forEach((c) => c.classList.toggle("filled", !!c.value));
      if (hidden.value.length === cells.length) form.requestSubmit();
    };
    const fill = (from, text) => {
      const digits = text.replace(/\D/g, "").split("");
      let i = from;
      for (const d of digits) { if (i >= cells.length) break; cells[i++].value = d; }
      cells[Math.min(i, cells.length - 1)].focus();
      sync();
    };
    cells.forEach((cell, i) => {
      cell.addEventListener("input", () => {
        const v = cell.value.replace(/\D/g, "");
        if (v.length > 1) return fill(i, v);
        cell.value = v;
        if (v && i < cells.length - 1) cells[i + 1].focus();
        sync();
      });
      cell.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && !cell.value && i > 0) { cells[i - 1].value = ""; cells[i - 1].focus(); sync(); }
        if (e.key === "ArrowLeft" && i > 0) cells[i - 1].focus();
        if (e.key === "ArrowRight" && i < cells.length - 1) cells[i + 1].focus();
      });
      cell.addEventListener("paste", (e) => { e.preventDefault(); fill(i, e.clipboardData.getData("text")); });
      cell.addEventListener("focus", () => cell.select());
    });
    if (wrap.dataset.error !== undefined) {
      wrap.classList.add("shake");
      cells.forEach((c) => (c.value = ""));
    }
    cells[0].focus();
  });

  // --- Qayta yuborish taymeri ---
  document.querySelectorAll("[data-countdown]").forEach((el) => {
    const btn = document.querySelector(el.dataset.target);
    let left = parseInt(el.dataset.countdown, 10);
    const tick = () => {
      if (left <= 0) { el.hidden = true; btn.disabled = false; return; }
      el.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
      btn.disabled = true; left -= 1; setTimeout(tick, 1000);
    };
    tick();
  });

  // --- Chop etish tugmasi (inline onclick CSP'da taqiqlangan) ---
  document.addEventListener("click", (e) => { if (e.target.closest("[data-print]")) window.print(); });

  // --- Shartnoma: oylik to'lovni jonli hisoblash (server bilan bir xil: so'mgacha yaxlitlash) ---
  document.querySelectorAll("[data-fee-calc]").forEach((form) => {
    const tariff = form.querySelector("[name$=full_tariff]");
    const discount = form.querySelector("[name$=discount_percent]");
    const out = form.querySelector("[data-fee-output]");
    const discountOut = form.querySelector("[data-discount-output]");
    const fmt = (n) => Math.round(n).toLocaleString("ru-RU").replace(/,/g, " ");
    const calc = () => {
      const t = parseFloat(tariff.value) || 0;
      const d = Math.min(100, Math.max(0, parseFloat(discount.value) || 0));
      const fee = Math.round((t * (100 - d)) / 100);
      out.textContent = fmt(fee);
      if (discountOut) discountOut.textContent = fmt(t - fee);
    };
    [tariff, discount].forEach((el) => el.addEventListener("input", calc));
    form.addEventListener("fee:recalc", calc);
    calc();
  });

  // --- Qabul formasi: vasiylarni yoqish/o'chirish, shartnoma vasiysi, sinf → grade va tarif ---
  document.querySelectorAll("[data-admission]").forEach((form) => {
    const slots = [...form.querySelectorAll("[data-slot]")];
    const signerLabels = [...form.querySelectorAll("[data-signer]")];
    const signerEmpty = form.querySelector("[data-signer-empty]");
    const syncSlots = () => {
      const enabled = new Set();
      slots.forEach((slot) => {
        const on = slot.querySelector("[data-slot-toggle]").checked;
        slot.querySelector("[data-slot-body]").hidden = !on;
        if (on) enabled.add(slot.dataset.slot);
      });
      signerLabels.forEach((label) => { label.hidden = !enabled.has(label.dataset.signer); });
      const checked = form.querySelector("[data-signer] input:checked");
      if (!checked || !enabled.has(checked.value)) {
        // Sukut: olib keluvchi (asosiy vasiy) → ota → ona
        const pick = ["carrier", "father", "mother"].find((k) => enabled.has(k));
        form.querySelectorAll("[data-signer] input").forEach((i) => { i.checked = i.value === pick; });
      }
      if (signerEmpty) signerEmpty.hidden = enabled.size > 0;
    };
    form.addEventListener("change", (e) => {
      if (e.target.matches("[data-slot-toggle]")) {
        syncSlots();
        if (e.target.checked) e.target.closest("[data-slot]").querySelector("[data-slot-body] input")?.focus();
      }
    });
    syncSlots();

    const classSel = form.querySelector("[data-class-select]");
    const grade = form.querySelector("[name$=grade]");
    const tariff = form.querySelector("[data-tariff-input]");
    classSel?.addEventListener("change", () => {
      const o = classSel.selectedOptions[0];
      if (o?.dataset.grade && grade) grade.value = o.dataset.grade;
      if (o?.dataset.tariff && tariff) {
        tariff.value = o.dataset.tariff;
        tariff.closest("[data-fee-calc]")?.dispatchEvent(new Event("fee:recalc"));
      }
    });
  });

  // --- Passport: avtomatik katta harf ---
  document.querySelectorAll("[data-upper]").forEach((el) =>
    el.addEventListener("input", () => { el.value = el.value.toUpperCase().replace(/\s/g, ""); }));

  // --- Select o'zgarganda formani yuborish (oy tanlash va h.k.) ---
  document.addEventListener("change", (e) => {
    if (e.target.matches("[data-autosubmit]")) e.target.form.requestSubmit();
  });

  // --- Ro'yxat filtrlari: "Filtr qo'shish" menyusi maydonni ochadi, × olib tashlaydi.
  //     So'rov faqat "Qidirish" bosilganda ketadi; qo'llanmagan o'zgarish bo'lsa tugma belgilanadi. ---
  document.querySelectorAll("[data-filter-form]").forEach((form) => {
    const fieldOf = (name) => form.querySelector(`.filter-field[data-filter="${name}"]`);
    const submitBtn = form.querySelector("[data-filter-submit]");
    const markPending = () => submitBtn?.classList.add("is-pending");
    form.addEventListener("change", markPending);
    form.addEventListener("click", (e) => {
      const add = e.target.closest("[data-filter-add]");
      if (add) {
        const field = fieldOf(add.dataset.filterAdd);
        field.hidden = false;
        add.closest("details").removeAttribute("open");
        field.querySelector("select, input").focus();
        return;
      }
      const remove = e.target.closest("[data-filter-remove]");
      if (remove) {
        const field = remove.closest(".filter-field");
        field.querySelectorAll("select, input").forEach((el) => { el.value = ""; });
        field.hidden = true;
        markPending();
      }
    });
    // Bo'sh maydonlar URL'ga tushmasin (?grade=&tariff=… o'rniga toza manzil).
    form.addEventListener("submit", () => {
      form.querySelectorAll("select, input").forEach((el) => {
        if (!el.value && !el.hasAttribute("data-keep-empty")) el.disabled = true;
      });
    });
    window.addEventListener("pageshow", () => form.querySelectorAll(":disabled").forEach((el) => { el.disabled = false; }));
  });

  // --- O'quvchi formasi: hujjat turi (metrika / passport) — faqat tanlangan maydon ko'rinadi ---
  document.querySelectorAll("[data-doc-switch]").forEach((wrap) => {
    const sync = () => {
      const chosen = wrap.querySelector("input[name$=doc_type]:checked")?.value || "birth_certificate";
      wrap.querySelectorAll("[data-doc]").forEach((el) => {
        // Qiymati bor maydon yashirilmaydi — ma'lumot ko'zdan "yo'qolib" qolmasin.
        el.hidden = el.dataset.doc !== chosen && !el.querySelector("input").value;
      });
    };
    wrap.addEventListener("change", (e) => { if (e.target.name?.endsWith("doc_type")) sync(); });
    sync();
  });

  // --- Manzil: viloyat → tuman (sahifadagi JSON'dan), tuman → mahallalar (serverdan, <datalist>) ---
  document.querySelectorAll("[data-address]").forEach((wrap) => {
    const region = wrap.querySelector("[data-region]");
    const district = wrap.querySelector("[data-district]");
    const mahalla = wrap.querySelector("[data-mahalla]");
    const list = document.getElementById(mahalla?.getAttribute("list"));
    const mapEl = document.getElementById("district-map");
    if (!region || !district || !mapEl) return;
    const map = JSON.parse(mapEl.textContent);
    const option = (value, text) => { const o = document.createElement("option"); o.value = value; o.textContent = text; return o; };
    const fillDistricts = () => {
      const names = map[region.value] || [];
      const keep = district.value;
      district.replaceChildren(option("", region.value ? "— Tanlang —" : "— Avval viloyatni tanlang —"),
        ...names.map((n) => option(n, n)));
      district.value = names.includes(keep) ? keep : "";
    };
    const loadMahallas = async () => {
      if (!list) return;
      list.replaceChildren();
      if (!district.value) return;
      const url = `${wrap.dataset.mahallaUrl}?${new URLSearchParams({ region: region.value, district: district.value })}`;
      try {
        const resp = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
        if (resp.ok) list.replaceChildren(...(await resp.json()).mahallas.map((n) => option(n, "")));
      } catch { /* taklifsiz ham yozish mumkin */ }
    };
    region.addEventListener("change", () => { fillDistricts(); if (mahalla) mahalla.value = ""; loadMahallas(); });
    district.addEventListener("change", () => { if (mahalla) mahalla.value = ""; loadMahallas(); });
  });

  // --- O'quv yili tanlanganda sinflar ro'yxati shu yilga saralanadi ---
  document.querySelectorAll("[data-year-select]").forEach((yearSel) => {
    const classSel = yearSel.form?.querySelector("[data-class-select]");
    if (!classSel) return;
    const sync = () => {
      [...classSel.options].forEach((o) => {
        if (!o.value) return;
        o.hidden = !!yearSel.value && o.dataset.year !== yearSel.value;
      });
      if (classSel.selectedOptions[0]?.hidden) classSel.value = "";
    };
    yearSel.addEventListener("change", sync);
    sync();
  });

  // --- Tahrirlash: yangi vasiy bloki ("Ota kiritilmagan" / "Yangi vasiy qo'shish") ---
  const newGuardian = document.querySelector("[data-new-guardian-box]");
  if (newGuardian) {
    const enabled = newGuardian.querySelector("[data-new-enabled]");
    document.addEventListener("click", (e) => {
      const open = e.target.closest("[data-new-guardian]");
      if (open) {
        newGuardian.hidden = false; enabled.value = "1";
        const radio = newGuardian.querySelector(`input[name$="relation"][value="${open.dataset.newGuardian}"]`);
        if (radio) radio.checked = true;
        newGuardian.querySelector("input[name$=last_name]").focus();
      } else if (e.target.closest("[data-new-guardian-cancel]")) {
        newGuardian.hidden = true; enabled.value = "0";
      }
    });
  }

  // --- Modal oynalar: <button data-open-dialog="id">, ichida [data-close-dialog] ---
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open-dialog]");
    if (opener) { document.getElementById(opener.dataset.openDialog)?.showModal(); return; }
    const closer = e.target.closest("[data-close-dialog]");
    if (closer) closer.closest("dialog")?.close();
    else if (e.target.matches("dialog.modal")) e.target.close();  // fon bosilganda
  });

  // --- URL'da oyna langari bo'lsa (#add-members) — sahifa ochilganda shu oyna ochiladi ---
  if (location.hash.length > 1) document.querySelector(`dialog.modal#${CSS.escape(location.hash.slice(1))}`)?.showModal();

  // --- Guruh formasi: tur o'zgarsa, stavka sukut qiymatlari (foydalanuvchi o'zgartirmagan bo'lsa) ---
  document.querySelectorAll("[data-group-form]").forEach((form) => {
    const DEFAULTS = { whole_class: ["per_lesson", "2400", "0"], subset: ["per_student", "120000", "15"] };
    const rate = form.querySelector("[data-group-rate]");
    const deduction = form.querySelector("[name=deduction_percent]");
    form.addEventListener("change", (e) => {
      if (!e.target.matches("[data-group-kind] input, input[data-group-kind]")) return;
      const other = Object.entries(DEFAULTS).find(([k]) => k !== e.target.value)[1];
      if (rate.value && rate.value !== other[1] && Number(rate.value) !== Number(other[1])) return;
      const [scheme, r, d] = DEFAULTS[e.target.value];
      form.querySelector(`[name=pay_scheme][value=${scheme}]`).checked = true;
      rate.value = r;
      deduction.value = d;
    });
  });

  // --- Qidiruvli ro'yxat: <input data-search-for="select-id"> mos kelmagan variantlarni yashiradi ---
  document.querySelectorAll("[data-search-for]").forEach((input) => {
    const select = document.getElementById(input.dataset.searchFor);
    if (!select) return;
    if (select.tagName !== "SELECT") {  // belgilash ro'yxati (.check-item) — mos kelmaganlar yashiriladi
      input.addEventListener("input", () => {
        const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
        select.querySelectorAll(".check-item, [data-search-item]").forEach((item) => {
          const text = item.textContent.toLowerCase();
          item.hidden = !terms.every((t) => text.includes(t)) && !item.querySelector("input:checked");
        });
      });
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });
      return;
    }
    input.addEventListener("input", () => {
      const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      [...select.options].forEach((o) => {
        if (!o.value) { o.hidden = terms.length > 0; return; }
        const text = o.textContent.toLowerCase();
        o.hidden = !terms.every((t) => text.includes(t));
      });
    });
    input.addEventListener("keydown", (e) => {  // Enter — birinchi mos variantni tanlaydi
      if (e.key !== "Enter") return;
      e.preventDefault();
      const first = [...select.options].find((o) => o.value && !o.hidden);
      if (first) { select.value = first.value; select.dispatchEvent(new Event("change", { bubbles: true })); }
    });
  });

  // --- Yangi shartnoma: o'quvchi tanlanganda — uning vasiylari va sinf tarifi ---
  document.querySelectorAll("[data-contract-new]").forEach((form) => {
    const dataEl = document.getElementById("contract-candidates");
    const student = form.querySelector("[data-contract-student]");
    const guardian = form.querySelector("[data-contract-guardian]");
    const tariff = form.querySelector("[data-tariff-input]");
    if (!dataEl || !student || !guardian) return;
    const map = JSON.parse(dataEl.textContent);
    const opt = (v, t) => { const o = document.createElement("option"); o.value = v; o.textContent = t; return o; };
    const sync = (initial) => {
      const info = map[student.value];
      const keep = guardian.value;
      if (!info) { guardian.replaceChildren(opt("", "Avval o'quvchini tanlang")); return; }
      guardian.replaceChildren(opt("", "— Asosiy vasiy —"),
        ...info.guardians.map(([id, name, primary]) => opt(id, primary ? `${name} (asosiy)` : name)));
      if (initial && keep) guardian.value = keep;
      if (!initial && info.tariff && tariff) {
        tariff.value = info.tariff;
        form.dispatchEvent(new Event("fee:recalc"));
      }
    };
    student.addEventListener("change", () => sync(false));
    sync(true);
  });

  // --- Dars qo'shish paneli (fragment yuklanadi — hodisalar hujjat darajasida): guruh → fanlari va xonasi ---
  document.addEventListener("change", (e) => {
    const groupSel = e.target.closest("[data-lesson-group]");
    if (!groupSel) return;
    const form = groupSel.closest("form");
    const map = JSON.parse(form.querySelector("#lesson-subjects")?.textContent || "{}");
    const info = map[groupSel.value];
    const subject = form.querySelector("[data-lesson-subject]");
    const opt = (v, t) => { const o = document.createElement("option"); o.value = v; o.textContent = t; return o; };
    subject.replaceChildren(opt("", "— Fan —"), ...(info?.subjects || []).map(([id, label]) => opt(id, label)));
    if (info?.subjects.length === 1) subject.value = info.subjects[0][0];
    const room = form.querySelector("[name=room]");
    if (room && info?.room) room.value = info.room;
  });

  // --- Xabar (toast) — JS'dan (masalan, sudrab qo'yishdagi xato) ---
  const toast = (text, isError) => {
    let box = document.querySelector(".toasts");
    if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("role", "status"); document.body.append(box); }
    const el = document.createElement("div");
    el.className = `toast${isError ? " error" : ""}`;
    el.textContent = text;
    box.append(el);
    setTimeout(() => el.remove(), 9000);
  };

  // --- Dars jadvali: karta/darsni katakka qo'yish — (1) bosib tanlash → katakni bosish, (2) sudrash.
  //     Qo'yilgach sahifa yangilanadi; aylantirish joyi va tanlangan karta saqlanib qoladi. ---
  document.querySelectorAll("[data-tt-board]").forEach((board) => {
    const csrf = board.querySelector("[name=csrfmiddlewaretoken]")?.value;
    const bar = document.querySelector("[data-placing-bar]");
    const hint = document.querySelector("[data-placing-hint]");
    const STATE = "tt:state";
    let picked = null;   // {url, groups?, subject?, name, el?} — bosib tanlangan karta yoki ko'chirilayotgan dars
    let dragged = null;  // sudralayotgan

    const setPicked = (next) => {
      document.querySelectorAll("[data-drag-card][aria-pressed=true]").forEach((c) => c.setAttribute("aria-pressed", "false"));
      picked = next;
      board.classList.toggle("is-placing", !!picked);
      if (bar) bar.hidden = !picked;
      if (hint) hint.hidden = !!picked;
      if (picked) {
        picked.el?.setAttribute("aria-pressed", "true");
        bar.querySelector("[data-placing-text]").textContent =
          `${picked.move ? "Ko'chirish" : "Qo'yish"}: «${picked.name}» — endi jadvaldagi katakni bosing`;
      }
    };
    const cardPayload = (card) => ({ url: board.dataset.placeUrl, groups: card.dataset.groups,
      subject: card.dataset.subject, name: card.dataset.name, el: card });

    const place = async (cell, what) => {
      cell.classList.add("is-busy");
      const body = new FormData();
      body.append("weekday", cell.dataset.weekday);
      body.append("slot", cell.dataset.slot);
      body.append("on", board.dataset.effective);
      if (what.groups) { body.append("groups", what.groups); body.append("subject", what.subject); }
      try {
        const resp = await fetch(what.url, { method: "POST", body, headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" } });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.ok) {
          // Yangilangach: shu joyga qaytamiz va (kartani qo'ygan bo'lsak) tanlovni davom ettiramiz
          try { sessionStorage.setItem(STATE, JSON.stringify({ y: scrollY, subject: what.groups ? what.subject : null })); } catch {}
          location.reload();
          return;
        }
        (data.errors || ["Saqlanmadi."]).forEach((m) => toast(m, true));
      } catch { toast("Server bilan aloqa yo'q. Qayta urinib ko'ring.", true); }
      cell.classList.remove("is-busy");
    };

    // Avvalgi holatni tiklash (qo'yishdan keyingi yangilanish)
    try {
      const st = JSON.parse(sessionStorage.getItem(STATE) || "null");
      sessionStorage.removeItem(STATE);
      if (st) {
        scrollTo(0, st.y || 0);
        const card = st.subject && document.querySelector(`[data-drag-card][data-subject="${st.subject}"]:not([disabled])`);
        if (card) setPicked(cardPayload(card));
      }
    } catch {}

    // (1) Bosib tanlash
    document.addEventListener("click", (e) => {
      const card = e.target.closest("[data-drag-card]");
      if (card && !card.disabled) { setPicked(picked?.el === card ? null : cardPayload(card)); return; }
      const mover = e.target.closest("[data-move-start]");
      if (mover) {
        mover.closest("dialog")?.close();
        setPicked({ url: mover.dataset.moveStart, name: mover.dataset.name, move: true });
        return;
      }
      if (e.target.closest("[data-placing-cancel]")) setPicked(null);
    });
    board.addEventListener("click", (e) => {
      if (!picked) return;
      const cell = e.target.closest("[data-drop]");
      if (!cell) return;
      e.preventDefault();
      e.stopPropagation();  // "+" yoki dars paneli ochilmasin — tanlangan karta qo'yiladi
      place(cell, picked);
      if (picked.move) setPicked(null);
    }, true);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && picked) setPicked(null); });

    // (2) Sudrash (+ ekran chetida avtomatik aylantirish)
    document.addEventListener("dragstart", (e) => {
      const card = e.target.closest("[data-drag-card][draggable=true]");
      const lesson = e.target.closest("[data-move-url]");
      if (card) dragged = cardPayload(card);
      else if (lesson) dragged = { url: lesson.dataset.moveUrl, el: lesson };
      else return;
      dragged.el.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", "lesson");
    });
    document.addEventListener("dragend", () => {
      dragged?.el.classList.remove("is-dragging");
      board.querySelectorAll(".is-over").forEach((c) => c.classList.remove("is-over"));
    });
    document.addEventListener("dragover", (e) => {
      if (!dragged) return;
      const edge = 90;
      if (e.clientY > innerHeight - edge) scrollBy(0, 18);
      else if (e.clientY < edge) scrollBy(0, -18);
    });
    board.addEventListener("dragover", (e) => {
      const cell = e.target.closest("[data-drop]");
      if (!cell || !dragged) return;
      e.preventDefault();
      board.querySelectorAll(".is-over").forEach((c) => { if (c !== cell) c.classList.remove("is-over"); });
      cell.classList.add("is-over");
    });
    board.addEventListener("dragleave", (e) => { e.target.closest("[data-drop]")?.classList.remove("is-over"); });
    board.addEventListener("drop", (e) => {
      const cell = e.target.closest("[data-drop]");
      if (!cell || !dragged) return;
      e.preventDefault();
      cell.classList.remove("is-over");
      const what = dragged;
      dragged = null;
      place(cell, what);
    });
  });

  // --- Formset: "qo'shish" — <template id="{prefix}-empty"> dan yangi qator; "olib tashlash" — DELETE belgisi ---
  document.addEventListener("click", (e) => {
    const add = e.target.closest("[data-formset-add]");
    if (add) {
      const prefix = add.dataset.formsetAdd;
      const total = document.querySelector(`[name=${prefix}-TOTAL_FORMS]`);
      const tpl = document.getElementById(`${prefix}-empty`);
      const list = document.querySelector(`[data-formset-list="${prefix}"]`);
      const n = Number(total.value);
      list.insertAdjacentHTML("beforeend", tpl.innerHTML.replaceAll("__prefix__", n));
      total.value = n + 1;
      list.lastElementChild.querySelector("select, input:not([type=hidden])")?.focus();
      return;
    }
    const del = e.target.closest("[data-formset-delete]");
    if (del) {
      const item = del.closest("[data-formset-item]");
      const box = item.querySelector("input[name$=DELETE]");
      if (box) box.checked = true;
      item.hidden = true;
    }
  });

  // --- Ko'p tanlovli filtr: tanlanganlar yozuvi ("Barchasi" yoki "Naqd, Bank") ---
  document.querySelectorAll("[data-multiselect]").forEach((box) => {
    const label = box.querySelector("[data-multiselect-label]");
    const sync = () => {
      const picked = [...box.querySelectorAll("input:checked")].map((i) => i.parentElement.textContent.trim());
      label.textContent = picked.length ? picked.join(", ") : label.dataset.empty;
      label.classList.toggle("is-empty", !picked.length);
    };
    box.addEventListener("change", sync);
    sync();
  });

  // --- Yon panel (<dialog class="side-panel">): [data-panel-url] kontentni serverdan oladi ---
  const sidePanel = document.getElementById("side-panel");
  if (sidePanel) {
    const body = sidePanel.querySelector("[data-panel-body]");
    document.addEventListener("click", async (e) => {
      const opener = e.target.closest("[data-panel-url]");
      if (!opener) return;
      e.preventDefault();
      body.innerHTML = '<p class="empty-line">Yuklanmoqda…</p>';
      if (!sidePanel.open) sidePanel.showModal();
      try {
        const resp = await fetch(opener.dataset.panelUrl, { headers: { "X-Requested-With": "fetch" } });
        if (!resp.ok) throw new Error(resp.status);
        body.innerHTML = await resp.text();  // o'z serverimizdagi shablon (skriptsiz)
        body.querySelector("[data-lesson-group]")?.dispatchEvent(new Event("change", { bubbles: true }));
        body.querySelector("input:not([type=hidden]), select")?.focus();
      } catch {
        body.innerHTML = '<p class="empty-line">Yuklab bo\'lmadi. Sahifani yangilab qayta urinib ko\'ring.</p>';
      }
    });
    sidePanel.addEventListener("click", (e) => { if (e.target === sidePanel) sidePanel.close(); });
  }

  // --- Tasdiqlash oynasi: <form data-confirm="..."> ---
  const confirmDialog = document.getElementById("confirm-dialog");
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (!form.matches("form[data-confirm]") || form.dataset.confirmed) return;
    e.preventDefault();
    if (!confirmDialog?.showModal) {
      if (window.confirm(form.dataset.confirm)) { form.dataset.confirmed = "1"; form.requestSubmit(); }
      return;
    }
    confirmDialog.querySelector("[data-confirm-text]").textContent = form.dataset.confirm;
    confirmDialog.querySelector("[data-confirm-ok]").textContent = form.dataset.confirmOk || "Ha";
    confirmDialog.onclose = () => {
      if (confirmDialog.returnValue === "ok") { form.dataset.confirmed = "1"; form.requestSubmit(); }
    };
    confirmDialog.returnValue = "";
    confirmDialog.showModal();
  });
  confirmDialog?.addEventListener("click", (e) => { if (e.target === confirmDialog) confirmDialog.close(); });

  // --- Yon panel (xarajat qo'shish) ---
  const drawer = document.getElementById("expense-drawer");
  if (drawer) {
    const backdrop = document.querySelector(".drawer-backdrop");
    const field = (name) => drawer.querySelector(`[data-f="${name}"]`);
    let lastTrigger = null;
    const open = () => {
      drawer.hidden = false; backdrop.hidden = false;
      requestAnimationFrame(() => drawer.classList.add("open"));
      document.body.classList.add("drawer-open");
      drawer.querySelector("[name=amount]").focus();
    };
    const close = () => {
      drawer.classList.remove("open"); backdrop.hidden = true; document.body.classList.remove("drawer-open");
      setTimeout(() => { drawer.hidden = true; }, 240);
      if (lastTrigger) lastTrigger.focus();
    };
    document.addEventListener("click", (e) => {
      const t = e.target.closest("[data-expense]");
      if (t) {
        e.preventDefault(); lastTrigger = t;
        field("category").value = t.dataset.category;
        field("name").textContent = t.dataset.name;
        field("icon").setAttribute("href", `#i-${t.dataset.icon}`);
        field("limit").textContent = t.dataset.limit;
        field("remaining").textContent = t.dataset.remaining;
        field("remaining").classList.toggle("text-danger", !!t.dataset.over);
        drawer.querySelectorAll(".field-error, .alert-error").forEach((el) => el.remove());
        drawer.querySelectorAll(".is-invalid").forEach((el) => el.classList.remove("is-invalid"));
        drawer.querySelector("form").reset();
        open();
      } else if (e.target.closest("[data-drawer-close]")) {
        close();
      }
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && drawer.classList.contains("open")) close(); });
    if (drawer.classList.contains("open")) { document.body.classList.add("drawer-open"); }
  }

  // --- Grafik tooltip'lari (chiziqli grafik: ustun bo'yicha; doiraviy: segment bo'yicha) ---
  const tipHTML = (head, rows) =>
    `<div class="tip-head"></div>${rows.map(() => '<div class="tip-row"><i></i><span></span><b></b></div>').join("")}`;
  const fillTip = (tip, head, rows) => {
    tip.innerHTML = tipHTML(head, rows);
    tip.querySelector(".tip-head").textContent = head;
    tip.querySelectorAll(".tip-row").forEach((row, i) => {
      row.querySelector("i").className = rows[i].cls;
      row.querySelector("span").textContent = rows[i].label;
      row.querySelector("b").textContent = rows[i].value;
    });
  };
  const place = (wrap, tip, x, y) => {
    const w = wrap.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = x + 14; if (left + tw > w) left = x - tw - 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${Math.max(0, y - th - 10)}px`;
  };

  document.querySelectorAll("[data-line-chart]").forEach((wrap) => {
    const svg = wrap.querySelector("svg"), tip = wrap.querySelector(".chart-tip");
    const guide = svg.querySelector(".guide");
    const labels = JSON.parse(wrap.dataset.series);
    const show = (col) => {
      const i = +col.dataset.i, d = labels[i];
      svg.querySelectorAll(".hot").forEach((el) => el.classList.remove("hot"));
      svg.querySelectorAll(`[data-i="${i}"]:not(.hover-col)`).forEach((el) => el.classList.add("hot"));
      guide.setAttribute("x1", col.dataset.x); guide.setAttribute("x2", col.dataset.x); guide.classList.add("show");
      fillTip(tip, d.label, [
        { cls: "seg-info", label: "Jami o'quvchilar", value: d.total },
        { cls: "seg-danger", label: "Ketganlar", value: d.left },
      ]);
      const r = svg.getBoundingClientRect(), scale = r.width / svg.viewBox.baseVal.width;
      place(wrap, tip, col.dataset.x * scale, col.dataset.y * scale + (r.top - wrap.getBoundingClientRect().top));
      tip.classList.add("show");
    };
    const hide = () => {
      tip.classList.remove("show"); guide.classList.remove("show");
      svg.querySelectorAll(".hot").forEach((el) => el.classList.remove("hot"));
    };
    svg.querySelectorAll(".hover-col").forEach((col) => {
      col.addEventListener("mouseenter", () => show(col));
      col.addEventListener("focus", () => show(col));
      col.addEventListener("blur", hide);
    });
    svg.addEventListener("mouseleave", hide);
  });

  document.querySelectorAll("[data-donut]").forEach((wrap) => {
    const svg = wrap.querySelector("svg"), tip = wrap.querySelector(".chart-tip");
    const show = (arc, x, y) => {
      svg.classList.add("has-hot");
      svg.querySelectorAll(".donut-arc").forEach((a) => a.classList.toggle("hot", a === arc));
      fillTip(tip, arc.dataset.label, [
        { cls: arc.dataset.cls, label: "O'quvchilar", value: arc.dataset.value },
        { cls: arc.dataset.cls, label: "Ulushi", value: `${arc.dataset.percent}%` },
      ]);
      place(wrap, tip, x, y);
      tip.classList.add("show");
    };
    const hide = () => {
      svg.classList.remove("has-hot"); tip.classList.remove("show");
      svg.querySelectorAll(".donut-arc").forEach((a) => a.classList.remove("hot"));
    };
    svg.querySelectorAll(".donut-arc").forEach((arc) => {
      arc.addEventListener("mousemove", (e) => {
        const r = wrap.getBoundingClientRect();
        show(arc, e.clientX - r.left, e.clientY - r.top);
      });
      arc.addEventListener("focus", () => show(arc, wrap.clientWidth / 2, wrap.clientHeight / 3));
      arc.addEventListener("blur", hide);
      arc.addEventListener("mouseleave", hide);
    });
  });

  // --- Yotoqxona davomati: katak → kichik menyu (B/Y/K/S/O) → saqlash, qator jamilari yangilanadi ---
  document.querySelectorAll("[data-att-board]").forEach((board) => {
    const pop = board.querySelector("[data-att-pop]");
    const csrf = board.querySelector("[name=csrfmiddlewaretoken]")?.value;
    let current = null;
    const close = () => { pop.hidden = true; current?.setAttribute("aria-expanded", "false"); current = null; };
    const recount = (row) => {
      row.querySelectorAll("[data-total]").forEach((td) => {
        td.textContent = row.querySelectorAll(`.att-cell[data-status="${td.dataset.total}"]`).length;
      });
    };
    board.addEventListener("click", async (e) => {
      const choice = e.target.closest("[data-set]");
      if (choice && current) {
        const cell = current, status = choice.dataset.set;
        close();
        const body = new FormData();
        body.append("student", cell.dataset.student); body.append("date", cell.dataset.date); body.append("status", status);
        cell.classList.add("is-saving");
        try {
          const resp = await fetch(board.dataset.markUrl, { method: "POST", body, headers: { "X-CSRFToken": csrf, "X-Requested-With": "fetch" } });
          const data = await resp.json();
          if (!resp.ok || !data.ok) throw new Error((data.errors || ["Saqlanmadi."]).join(" "));
          cell.dataset.status = status;
          cell.className = "att-cell " + (status ? "att-" + status : "att-empty");
          cell.textContent = status || "O";
          recount(cell.closest("[data-att-row]"));
        } catch (err) {
          toast(err.message || "Saqlanmadi.", true);
        } finally {
          cell.classList.remove("is-saving");
          cell.focus();
        }
        return;
      }
      const cell = e.target.closest("button.att-cell[data-student]");
      if (!cell) { if (!e.target.closest("[data-att-pop]")) close(); return; }
      if (current === cell) { close(); return; }
      close();
      current = cell;
      cell.setAttribute("aria-expanded", "true");
      pop.hidden = false;
      const b = board.getBoundingClientRect(), c = cell.getBoundingClientRect();
      const left = Math.min(Math.max(8, c.left - b.left + c.width / 2 - pop.offsetWidth / 2), b.width - pop.offsetWidth - 8);
      pop.style.left = left + "px";
      pop.style.top = (c.bottom - b.top + 6) + "px";
      pop.querySelector(`[data-set="${cell.dataset.status}"]`)?.focus();
    });
    // Eng so'nggi kunlar (bugun) ko'rinsin: keng jadval o'ngga surilgan holda ochiladi
    const wrap = board.querySelector(".table-wrap");
    if (wrap) {
      wrap.scrollLeft = wrap.scrollWidth;
      wrap.addEventListener("scroll", close, { passive: true });
    }
    document.addEventListener("click", (e) => { if (!board.contains(e.target)) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && current) { const c = current; close(); c.focus(); } });
  });

  // --- Kunlik belgilash: tanlangan belgini ajratib ko'rsatish, "belgilanmaganlar — Bor" ---
  document.querySelectorAll("[data-att-day]").forEach((form) => {
    const sync = (group) => group.querySelectorAll("label").forEach((l) => l.classList.toggle("is-on", l.querySelector("input").checked));
    form.addEventListener("change", (e) => { const g = e.target.closest(".att-choice"); if (g) sync(g); });
    form.querySelector("[data-att-all]")?.addEventListener("click", (e) => {
      const value = e.currentTarget.dataset.attAll;
      form.querySelectorAll(".att-choice").forEach((g) => {
        const empty = g.querySelector('input[value=""]');
        if (empty.checked) { g.querySelector(`input[value="${value}"]`).checked = true; sync(g); }
      });
    });
  });

  // --- Sinf rahbarlik: katak bosilganda holat aylanadi (bo'sh → ✓ → ✗ → K → S), «Hammasi keldi» ---
  document.querySelectorAll("[data-homeroom-day]").forEach((form) => {
    const order = ["", "B", "Y", "K", "S"];
    const symbol = { "": "–", B: "✓", Y: "✗", K: "K", S: "S" };
    const label = { "": "belgilanmagan", B: "Keldi", Y: "Kelmadi", K: "Kechikdi", S: "Sababli" };
    const set = (btn, value) => {
      const input = btn.parentElement.querySelector("input[type=hidden]");
      input.value = value;
      btn.className = "att-cell hr-mark " + (value ? "att-" + value : "att-empty");
      btn.textContent = symbol[value];
      btn.setAttribute("aria-label", btn.getAttribute("aria-label").replace(/: .*$/, ": " + label[value]));
    };
    form.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-hr-mark]");
      if (btn) {
        const current = btn.parentElement.querySelector("input[type=hidden]").value;
        set(btn, order[(order.indexOf(current) + 1) % order.length]);
        return;
      }
      if (e.target.closest("[data-hr-all]")) {
        form.querySelectorAll("[data-hr-mark]").forEach((b) => {
          if (!b.parentElement.querySelector("input[type=hidden]").value) set(b, "B");
        });
      }
    });
  });
  document.querySelectorAll("[data-date-nav]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.value) window.location.href = `${input.dataset.dateNav}?date=${input.value}`;
    });
  });

  // --- Ish haqi qoidalari: formula bo'laklari, o'quvchi ulushi va avans kalkulyatorlari ---
  document.querySelectorAll("[data-rules]").forEach((root) => {
    const fmt = (n) => `${Math.round(n).toLocaleString("ru-RU").replace(/\u00a0/g, " ")} so'm`;
    const num = (el) => Number(String(el.value).replace(/\D/g, "")) || 0;

    root.querySelectorAll("[data-formula]").forEach((btn) => btn.addEventListener("click", () => {
      root.querySelectorAll("[data-formula]").forEach((b) => {
        const on = b === btn;
        b.setAttribute("aria-selected", on ? "true" : "false");
        document.getElementById(b.dataset.formula).hidden = !on;
      });
    }));

    const share = root.querySelector("[data-share-calc]");
    if (share) {
      const q = (sel) => share.querySelector(sel);
      const run = () => {
        const scheme = q("[data-share-scheme]:checked").value;
        share.querySelectorAll("[data-only]").forEach((el) => (el.hidden = el.dataset.only !== scheme));
        const tariff = num(q("[data-share-tariff]"));
        const due = tariff * (1 - Math.min(100, num(q("[data-share-discount]"))) / 100);
        const paidPct = Number(q("[data-share-paid]").value);
        const paid = (due * paidPct) / 100;
        const ratio = tariff ? paid / tariff : 0;
        const maxRatio = tariff ? due / tariff : 0;
        let k;
        if (scheme === "lesson") k = num(q("[data-share-lessons]")) * num(q("[data-share-rate-lesson]"));
        else k = num(q("[data-share-rate-student]")) * (1 - Math.min(100, num(q("[data-share-cut]"))) / 100);
        q("[data-share-paid-out]").textContent = paidPct + "%";
        q("[data-share-due]").textContent = fmt(due);
        q("[data-share-paid-sum]").textContent = fmt(paid);
        q("[data-share-ratio]").textContent = (ratio * 100).toFixed(1).replace(".0", "") + "%";
        q("[data-share-you]").textContent = fmt(k * ratio);
        q("[data-share-max]").textContent = fmt(k * maxRatio);
      };
      share.addEventListener("input", run);
      share.addEventListener("change", run);
      run();
    }

    const adv = root.querySelector("[data-advance-calc]");
    if (adv) {
      const total = adv.querySelector("[data-adv-total]");
      const pct = adv.querySelector("[data-adv-pct]");
      const run = () => {
        const t = num(total);
        const a = Math.floor((t * Number(pct.value)) / 100 / 1000) * 1000;
        const rest = t - a;
        const final = Math.floor(rest / 1000) * 1000;
        adv.querySelector("[data-adv-pct-out]").textContent = pct.value + "%";
        adv.querySelector("[data-adv-sum]").textContent = fmt(a);
        adv.querySelector("[data-adv-final]").textContent = fmt(final);
        adv.querySelector("[data-adv-carry]").textContent = fmt(rest - final);
      };
      total.addEventListener("input", () => {
        const d = total.value.replace(/\D/g, "").slice(0, 12);
        total.value = d ? Number(d).toLocaleString("ru-RU").replace(/\u00a0/g, " ") : "";
        run();
      });
      pct.addEventListener("input", run);
      run();
    }
  });

  // --- Toastlar avtomatik yo'qoladi ---
  document.querySelectorAll(".toast").forEach((t) => setTimeout(() => t.remove(), 4500));
})();
