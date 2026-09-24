const screenshotButtons = [...document.querySelectorAll("[data-screenshot]")];
const screenshotDialog = document.getElementById("screenshot-dialog");
const dialogImage = document.getElementById("screenshot-dialog-image");
const dialogTitle = document.getElementById("screenshot-dialog-title");
const dialogCount = document.getElementById("screenshot-dialog-count");
const fullResolutionLink = document.getElementById(
  "screenshot-full-resolution",
);
const screenshotTitles = {
  research: "Research workspace",
  market: "Market observation",
  account: "Account perspective",
};
let screenshotIndex = 0;
let screenshotTrigger;

function showScreenshot(index) {
  screenshotIndex =
    (index + screenshotButtons.length) % screenshotButtons.length;
  const button = screenshotButtons[screenshotIndex];
  const source = button.querySelector("img");
  dialogImage.src = source.src;
  dialogImage.alt = source.alt;
  dialogImage.width = Number(source.getAttribute("width"));
  dialogImage.height = Number(source.getAttribute("height"));
  dialogTitle.textContent = screenshotTitles[button.dataset.screenshot];
  dialogCount.textContent = `${String(screenshotIndex + 1).padStart(2, "0")} / ${String(screenshotButtons.length).padStart(2, "0")}`;
  fullResolutionLink.href = source.src;
}

for (const [index, button] of screenshotButtons.entries()) {
  button.addEventListener("click", () => {
    screenshotTrigger = button;
    showScreenshot(index);
    screenshotDialog.showModal();
    document.documentElement.classList.add("screenshot-open");
  });
}

screenshotDialog
  .querySelector(".screenshot-dialog-close")
  .addEventListener("click", () => {
    screenshotDialog.close();
  });
screenshotDialog
  .querySelector("[data-gallery-previous]")
  .addEventListener("click", () => {
    showScreenshot(screenshotIndex - 1);
  });
screenshotDialog
  .querySelector("[data-gallery-next]")
  .addEventListener("click", () => {
    showScreenshot(screenshotIndex + 1);
  });
screenshotDialog.addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    showScreenshot(screenshotIndex + (event.key === "ArrowRight" ? 1 : -1));
  }
});
screenshotDialog.addEventListener("click", (event) => {
  if (event.target !== screenshotDialog) return;
  const bounds = screenshotDialog.getBoundingClientRect();
  if (
    event.clientX < bounds.left ||
    event.clientX > bounds.right ||
    event.clientY < bounds.top ||
    event.clientY > bounds.bottom
  ) {
    screenshotDialog.close();
  }
});
screenshotDialog.addEventListener("close", () => {
  document.documentElement.classList.remove("screenshot-open");
  screenshotTrigger?.focus({ preventScroll: true });
});
