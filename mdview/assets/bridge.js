"use strict";
document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-copy]");
  if (!button || !event.isTrusted) return;
  window.webkit.messageHandlers.copy.postMessage(Number(button.dataset.copy));
});
window.mdviewCopied = (index) => {
  const button = document.querySelector(`button[data-copy="${index}"]`);
  if (!button) return;
  button.textContent = "Copied";
  setTimeout(() => { button.textContent = "Copy"; }, 1400);
};
