// Forms that call the AI service can take several seconds. Show that something is
// happening and stop a second click from submitting the same record twice.
document.querySelectorAll("form[data-busy-text]").forEach(function (form) {
  var button = form.querySelector("button[type=submit]");
  if (!button) {
    return;
  }
  var originalText = button.textContent;

  form.addEventListener("submit", function () {
    button.disabled = true;
    button.textContent = form.dataset.busyText;
  });

  // Restore the button if the browser shows this page again from its back/forward cache.
  window.addEventListener("pageshow", function () {
    button.disabled = false;
    button.textContent = originalText;
  });
});
