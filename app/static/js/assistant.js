// Persist the assistant panel's custom size (per user) when the user drags the
// CSS resize handle. Debounced so we only save once dragging settles.
(function () {
  const panel = document.getElementById("assistant");
  if (!panel) return;

  let timer = null;
  let lastSaved = { width: 0, height: 0 };

  function save() {
    const width = Math.round(panel.getBoundingClientRect().width);
    const height = Math.round(panel.getBoundingClientRect().height);
    if (width === lastSaved.width && height === lastSaved.height) return;
    lastSaved = { width, height };
    fetch("/assistant/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ width, height }),
    }).catch(function () {
      /* best-effort; ignore network errors */
    });
  }

  const observer = new ResizeObserver(function () {
    if (timer) clearTimeout(timer);
    timer = setTimeout(save, 600);
  });
  observer.observe(panel);

  // Keep the chat scrolled to the latest message.
  const log = panel.querySelector(".chat-log");
  if (log) log.scrollTop = log.scrollHeight;
})();
