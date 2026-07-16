// Keep the assistant chat scrolled to the latest message on load.
(function () {
  const log = document.querySelector("#assistant .chat-log");
  if (log) log.scrollTop = log.scrollHeight;

  // Beginner starter prompts: clicking a chip fills the chat box.
  const box = document.getElementById("question-box");
  document.querySelectorAll(".chip[data-prompt]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      if (!box) return;
      box.value = chip.getAttribute("data-prompt");
      box.focus();
    });
  });
})();
