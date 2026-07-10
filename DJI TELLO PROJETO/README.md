# DJI Tello Web Dashboard

Interface web local para controlar um DJI Tello no Windows com Flask, Flask-SocketIO, djitellopy, OpenCV e YOLOv8n.

## Instalar

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Executar

Antes de conectar o Windows ao Wi-Fi do Tello, baixe os modelos para uso offline:

```powershell
python setup_models.py
```

Depois conecte o Windows ao Wi-Fi do Tello e rode:

```powershell
python app.py
```

Abra `http://localhost:5000`.

Fotos ficam em `media/photos/` e videos em `media/videos/`. Screenshots automaticos de fogo tambem ficam em `media/photos/`.

O Tello nao tem GPS; a distancia exibida e estimada por odometria integrando `vgx`, `vgy` e `vgz`. A altura da sessao tambem e acumulada por odometria e so volta para zero quando o comando de pouso ou emergencia e executado. O RSSI do SDK nao existe, entao o app tenta ler o sinal Wi-Fi via `netsh` no Windows e, se falhar, usa uma estimativa pela qualidade do stream.

O modelo de pessoas usa YOLOv8n COCO salvo em `models/person_yolov8n.pt`. O modelo de fogo usa um peso YOLOv8n de fogo/fumaca salvo em `models/fire_yolov8n.pt` e o app filtra a classe de fogo.

## Estrutura do codigo

- `config.py` - caminhos, variaveis de ambiente e limiares de seguranca.
- `extensions.py` - instancia compartilhada do Flask-SocketIO.
- `dashboard.py` - toda a logica do drone (`TelloDashboard`): conexao, video, deteccao, telemetria, failsafes.
- `app.py` - rotas Flask, handlers de socket e ponto de entrada (`python app.py`).
- `generate_cert.py` - gera certificado HTTPS local (necessario para o modo VR).
- `templates/vr.html` + `static/js/vr.js` - cena WebXR do modo imersivo.

## Seguranca de voo

- **Watchdog de comando**: se nenhum comando chegar do navegador por `TELLO_COMMAND_TIMEOUT` segundos (padrao 8s) enquanto o drone esta voando, ele pousa sozinho.
- **Bateria**: abaixo de `TELLO_BATTERY_WARNING_PCT` (padrao 20%) so avisa; abaixo de `TELLO_BATTERY_CRITICAL_PCT` (padrao 10%) pousa automaticamente.
- **Limite de disco**: `media/photos` e `media/videos` mantem so os `TELLO_MAX_PHOTOS`/`TELLO_MAX_VIDEOS` arquivos mais recentes, apagando os mais antigos.

Todos esses valores podem ser ajustados copiando `.env.example` para `.env`.

## Testes

```powershell
pip install -r requirements-dev.txt
pytest
```

Cobrem odometria, geracao de CSV e os failsafes de seguranca (sem precisar do drone fisico conectado).

## Modo VR (Meta Quest 3S)

O dashboard tem uma versao imersiva em `/vr`: o stream da camera aparece numa tela flutuante
dentro do headset, com telemetria sobreposta (HUD) e os controllers mapeados pra mover o drone.

### 1. Gerar o certificado HTTPS (obrigatorio)

WebXR so funciona em HTTPS (exceto em `localhost`). Rode uma vez:

```powershell
pip install cryptography
python generate_cert.py
```

Isso detecta os IPs da sua maquina e gera `certs/server.crt` e `certs/server.key`. A partir
dai, `python app.py` sobe automaticamente em HTTPS (o terminal avisa qual modo esta ativo).

### 2. Testar sem o headset

Instale a extensao **"Immersive Web Emulator"** no Chrome desktop (simula o Quest e os
controllers). Com o servidor rodando, abra `https://localhost:5000/vr`, aceite o aviso de
certificado autoassinado, ative o emulador e clique em "Entrar em VR".

### 3. Usando com o Quest 3S de verdade

1. Conecte o PC ao Wi-Fi do Tello (assim como no modo 2D normal).
2. No navegador do Quest, abra `https://<ip-do-pc>:5000/vr` (o IP aparece no terminal quando
   `python app.py` sobe).
3. Aceite o aviso de certificado nao confiavel (e autoassinado, esperado) - "Avancado" >
   "Continuar mesmo assim".
4. Toque em "Entrar em VR".

Mapeamento padrao dos controllers (ajustavel em `static/js/vr.js`, indices de botao podem
variar por firmware - abra `/vr?debug=1` pra ver o estado bruto no console e recalibrar):

- Thumbstick esquerdo: mover (frente/tras/esquerda/direita).
- Thumbstick direito: subir/descer e girar (yaw).
- Gatilho direito: foto.
- Grip direito: gravar/parar gravacao.
- Botao A (esquerdo): decolar.
- Botao B (esquerdo): pousar.

Os mesmos failsafes de seguranca do modo 2D (watchdog de comando e bateria critica) continuam
valendo no modo VR, porque rodam no servidor.

**Nota sobre internet**: o Tello cria sua propria rede Wi-Fi sem internet. O Three.js do modo VR
ja vem vendorizado em `static/vendor/three.min.js` (nao depende de CDN), entao o `/vr` funciona
mesmo com o Quest conectado direto na rede do Tello, sem internet.
