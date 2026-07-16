// Keep the assistant chat scrolled to the latest message on load.
(function () {
  const log = document.querySelector("#assistant .chat-log");
  if (log) log.scrollTop = log.scrollHeight;
})();
