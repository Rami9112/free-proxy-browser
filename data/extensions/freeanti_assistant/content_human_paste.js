// freeanti Human-Typing Paste Emulation (Alt+P)
(function() {
  async function typeLikeHuman(el, text) {
    if (!el || !text) return;
    el.focus();
    for (const ch of text) {
      const opts = { key: ch, code: `Key${ch.toUpperCase()}`, bubbles: true, cancelable: true };
      el.dispatchEvent(new KeyboardEvent("keydown", opts));
      el.dispatchEvent(new KeyboardEvent("keypress", opts));
      if ("value" in el) {
        const start = el.selectionStart ?? el.value.length;
        const end = el.selectionEnd ?? el.value.length;
        const proto = el instanceof HTMLTextAreaElement
          ? window.HTMLTextAreaElement.prototype
          : window.HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        const nextVal = el.value.slice(0, start) + ch + el.value.slice(end);
        if (setter) setter.call(el, nextVal);
        else el.value = nextVal;
        try { el.setSelectionRange(start + 1, start + 1); } catch {}
      } else if (el.isContentEditable) {
        document.execCommand("insertText", false, ch);
      }
      el.dispatchEvent(new InputEvent("input", { data: ch, inputType: "insertText", bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", opts));
      await new Promise(r => setTimeout(r, 25 + Math.floor(Math.random() * 45)));
    }
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  window.addEventListener("keydown", async (e) => {
    if (e.altKey && (e.key === "p" || e.key === "P")) {
      e.preventDefault();
      try {
        const text = await navigator.clipboard.readText();
        await typeLikeHuman(document.activeElement, text);
      } catch (err) {
        console.warn("[freeanti] Clipboard read failed for Alt+P human typing:", err);
      }
    }
  }, true);
})();
