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

  // --- Toastlar avtomatik yo'qoladi ---
  document.querySelectorAll(".toast").forEach((t) => setTimeout(() => t.remove(), 4500));
})();
