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

// Revelação premium: a cortina e o conteúdo acompanham o progresso real do
// scroll (não é só um "liga/desliga"), enquanto os cards ganham um leve
// desfoque na entrada, em cascata.
const revealEls = document.querySelectorAll(".reveal");
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function updateRevealProgress() {
  const vh = window.innerHeight;
  const start = vh * 0.92; // topo do elemento entra aqui = progresso 0
  const end = vh * 0.42; // topo do elemento chega aqui = progresso 1
  revealEls.forEach((el) => {
    const rect = el.getBoundingClientRect();
    let raw = (start - rect.top) / (start - end);
    raw = Math.min(1, Math.max(0, raw));
    el.style.setProperty("--p", easeOutCubic(raw).toFixed(4));
  });
}

let revealTicking = false;
function onRevealScroll() {
  if (revealTicking) return;
  revealTicking = true;
  requestAnimationFrame(() => {
    updateRevealProgress();
    revealTicking = false;
  });
}

if (revealEls.length) {
  if (prefersReducedMotion) {
    revealEls.forEach((el) => el.style.setProperty("--p", 1));
  } else {
    window.addEventListener("scroll", onRevealScroll, { passive: true });
    window.addEventListener("resize", onRevealScroll);
    updateRevealProgress();
  }
}

// Cascata dos cards (dispara uma vez, quando a seção entra na tela)
if (revealEls.length && !prefersReducedMotion && "IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          obs.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: "0px 0px -80px 0px" }
  );
  revealEls.forEach((el) => revealObserver.observe(el));
} else {
  revealEls.forEach((el) => el.classList.add("is-visible"));
}

// Barra de progresso de leitura no topo da página
const scrollProgressBar = document.getElementById("scrollProgress");
if (scrollProgressBar) {
  const updateProgressBar = () => {
    const doc = document.documentElement;
    const max = doc.scrollHeight - doc.clientHeight;
    const pct = max > 0 ? (doc.scrollTop / max) * 100 : 0;
    scrollProgressBar.style.width = `${pct}%`;
  };
  window.addEventListener("scroll", updateProgressBar, { passive: true });
  window.addEventListener("resize", updateProgressBar);
  updateProgressBar();
}

// Brilho seguindo o cursor nos cards
if (!prefersReducedMotion && window.matchMedia("(hover: hover)").matches) {
  document.querySelectorAll(".value-card, .feature-card, .req-card, .team-card").forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * 100;
      const y = ((event.clientY - rect.top) / rect.height) * 100;
      card.style.setProperty("--mx", `${x}%`);
      card.style.setProperty("--my", `${y}%`);
    });
  });

  // Leve inclinação 3D nos cards de recursos, seguindo o mouse
  document.querySelectorAll(".feature-card").forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      const px = (event.clientX - rect.left) / rect.width - 0.5;
      const py = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.transform = `perspective(700px) rotateX(${(py * -7).toFixed(2)}deg) rotateY(${(px * 7).toFixed(2)}deg) translateY(-2px)`;
    });
    card.addEventListener("mouseleave", () => {
      card.style.transform = "";
    });
  });
}

// Navbar com sombra ao rolar
const nav = document.getElementById("nav");
if (nav) {
  window.addEventListener("scroll", () => {
    nav.style.boxShadow = window.scrollY > 8 ? "0 8px 24px rgba(0,0,0,0.35)" : "none";
  });
}
