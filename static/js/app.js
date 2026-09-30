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

  // --- Toastlar avtomatik yo'qoladi ---
  document.querySelectorAll(".toast").forEach((t) => setTimeout(() => t.remove(), 4500));
})();
