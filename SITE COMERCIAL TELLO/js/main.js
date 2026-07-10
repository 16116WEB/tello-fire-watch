// Ano no rodape
const yearEl = document.getElementById("year");
if (yearEl) yearEl.textContent = new Date().getFullYear();

// Menu mobile
const navToggle = document.getElementById("navToggle");
const navLinks = document.getElementById("navLinks");

if (navToggle && navLinks) {
  navToggle.addEventListener("click", () => {
    const isOpen = navLinks.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  navLinks.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navLinks.classList.remove("open");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });
}

// FAQ accordion
document.querySelectorAll(".faq-item").forEach((item) => {
  const question = item.querySelector(".faq-question");
  const answer = item.querySelector(".faq-answer");
  if (!question || !answer) return;

  question.addEventListener("click", () => {
    const isOpen = item.classList.contains("open");

    document.querySelectorAll(".faq-item.open").forEach((openItem) => {
      if (openItem !== item) {
        openItem.classList.remove("open");
        openItem.querySelector(".faq-question").setAttribute("aria-expanded", "false");
        openItem.querySelector(".faq-answer").style.maxHeight = null;
      }
    });

    if (isOpen) {
      item.classList.remove("open");
      question.setAttribute("aria-expanded", "false");
      answer.style.maxHeight = null;
    } else {
      item.classList.add("open");
      question.setAttribute("aria-expanded", "true");
      answer.style.maxHeight = `${answer.scrollHeight}px`;
    }
  });
});

// Botao de download (placeholder ate o instalador existir)
const downloadBtn = document.getElementById("downloadBtn");
if (downloadBtn) {
  downloadBtn.addEventListener("click", (event) => {
    if (downloadBtn.getAttribute("href") === "#") {
      event.preventDefault();
      window.alert(
        "O instalador ainda nao foi publicado. Troque o href de #downloadBtn no index.html pelo link real assim que o .exe estiver pronto."
      );
    }
  });
}

// Navbar com sombra ao rolar
const nav = document.getElementById("nav");
if (nav) {
  window.addEventListener("scroll", () => {
    nav.style.boxShadow = window.scrollY > 8 ? "0 8px 24px rgba(0,0,0,0.35)" : "none";
  });
}
