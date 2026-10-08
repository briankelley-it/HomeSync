// HouseLedger UI behaviour: theme toggle, mobile sidebar, and HTMX-driven dialogs.
(function () {
  "use strict";

  // ----- Theme -------------------------------------------------------------
  function setTheme(dark) {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch (e) {}
    document.dispatchEvent(new CustomEvent("themechange", { detail: { dark: dark } }));
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-theme-toggle]")) {
      setTheme(!document.documentElement.classList.contains("dark"));
    }
  });

  // ----- Mobile sidebar ----------------------------------------------------
  function toggleSidebar(open) {
    var sidebar = document.getElementById("sidebar");
    var backdrop = document.getElementById("sidebar-backdrop");
    if (!sidebar) return;
    sidebar.classList.toggle("-translate-x-full", !open);
    backdrop.classList.toggle("hidden", !open);
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-sidebar-open]")) toggleSidebar(true);
    if (event.target.closest("[data-sidebar-close]")) toggleSidebar(false);
  });

  // ----- Dialogs -----------------------------------------------------------
  // Buttons with hx-get + hx-target="#modal-content" load a form into the
  // shared <dialog>. The server responds with HX-Trigger: closeModal on success.
  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id === "modal-content") {
      var dialog = document.getElementById("modal");
      if (!dialog.open) dialog.showModal();
      var first = dialog.querySelector("input:not([type=hidden]), select, textarea");
      if (first) first.focus();
    }
  });

  document.addEventListener("closeModal", function () {
    var dialog = document.getElementById("modal");
    if (dialog && dialog.open) dialog.close();
  });

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-modal-close]")) {
      document.getElementById("modal").close();
    }
    // Clicking the backdrop closes the dialog.
    if (event.target.tagName === "DIALOG") event.target.close();
  });

  // Confirm destructive HTMX actions with the native dialog.
  document.addEventListener("htmx:confirm", function (event) {
    var message = event.detail.elt.getAttribute("hx-confirm");
    if (!message) return;
    event.preventDefault();
    if (window.confirm(message)) event.detail.issueRequest(true);
  });
})();
