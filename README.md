# Tello Fire Watch

Projeto acadêmico da Mostra STEAM: um painel web local para o DJI Tello com detecção de
pessoas e fogo em tempo real, trilha de voo, failsafes de segurança e modo imersivo em VR.

Este repositório tem duas partes independentes:

## [`DJI TELLO PROJETO/`](./DJI%20TELLO%20PROJETO)

O aplicativo em si — Flask + Flask-SocketIO + djitellopy + OpenCV + YOLOv8n. Roda localmente
no PC conectado ao Wi-Fi do drone e serve o painel de controle no navegador (2D e VR).

Instruções completas de instalação, configuração e testes estão no
[README dele](./DJI%20TELLO%20PROJETO/README.md).

## [`SITE COMERCIAL TELLO/`](./SITE%20COMERCIAL%20TELLO)

Site institucional estático (HTML/CSS/JS puro) apresentando o produto: recursos, segurança,
requisitos, FAQ e link de download. Pode ser hospedado em qualquer serviço de site estático
(ex: Render, GitHub Pages, Netlify) — não depende do backend do drone para funcionar.

Basta abrir `SITE COMERCIAL TELLO/index.html` no navegador para visualizar localmente.

## Sobre

Desenvolvido como projeto acadêmico para a Mostra STEAM, unindo visão computacional,
robótica aérea e desenvolvimento web num produto funcional de ponta a ponta.
