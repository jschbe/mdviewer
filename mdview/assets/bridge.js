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

// Keep the same block at the top after WebKit reflows the page at a new zoom.
window.mdviewZoomPosition = () => {
  const blocks = [...document.querySelector("main").children];
  let index = 0;
  for (let i = 0; i < blocks.length; i++) {
    if (blocks[i].getBoundingClientRect().top > 0) break;
    index = i;
  }
  const rect = blocks[index]?.getBoundingClientRect();
  return rect ? [index, -rect.top / Math.max(rect.height, 1), window.scrollX] : null;
};
window.mdviewRestoreZoomPosition = ([index, offset, x]) => {
  requestAnimationFrame(() => {
    const block = document.querySelector("main").children[index];
    if (!block) return;
    const rect = block.getBoundingClientRect();
    window.scrollTo(x, window.scrollY + rect.top + offset * rect.height);
  });
};
