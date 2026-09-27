/*
 * SPDX-FileCopyrightText: 2026 Jochen Schmitt
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

"use strict";
document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-copy]");
  if (!button || !event.isTrusted) return;
  window.webkit.messageHandlers.copy.postMessage(Number(button.dataset.copy));
});
window.mdviewCopied = (index) => {
  const button = document.querySelector(`button[data-copy="${index}"]`);
  if (!button) return;
  button.textContent = button.dataset.copiedLabel;
  setTimeout(() => { button.textContent = button.dataset.copyLabel; }, 1400);
};
