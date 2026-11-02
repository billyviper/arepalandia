#!/usr/bin/env bash
# Instalador del servidor de pedidos de Arepalandia (Ubuntu).
#
# Uso, en la compu servidor, con el usuario "arepalandia":
#   curl -fsSL https://raw.githubusercontent.com/billyviper/arepalandia/main/pedidos/instalar.sh -o instalar.sh
#   bash instalar.sh                          # instala o actualiza todo
#   bash instalar.sh tunel pedidos.midominio.com   # conecta el dominio (una sola vez, cuando lo tengan)
#
# Qué deja andando:
#   - el servidor de pedidos como servicio (arranca solo al prender la compu y se reinicia si falla)
#   - una copia de seguridad diaria de los datos en ~/respaldos (guarda 30 días)
#   - la compu sin suspenderse
#   - el túnel de Cloudflare para que el link funcione desde internet
set -euo pipefail

REPO="https://github.com/billyviper/arepalandia.git"
DIR="$HOME/arepalandia"
APP="$DIR/pedidos"
PUERTO=8080
USUARIO="$(id -un)"

paso() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m    %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then
  echo "Corré el instalador con tu usuario normal (sin sudo). Te va a pedir la contraseña cuando haga falta."
  exit 1
fi

instalar_base() {
  paso "Instalando programas necesarios"
  sudo apt-get update -qq
  sudo apt-get install -y -qq git python3 curl ca-certificates tzdata >/dev/null
  sudo timedatectl set-timezone America/Montevideo || true
  ok "Listo"

  paso "Descargando o actualizando el sistema de pedidos"
  if [ -d "$DIR/.git" ]; then
    git -C "$DIR" pull -q --ff-only
  else
    git clone -q "$REPO" "$DIR"
  fi
  ok "Código en $DIR"
}

configurar() {
  if [ -f "$APP/config.json" ]; then
    ok "config.json ya existe: no lo toco"
    return
  fi
  paso "Configuración (solo la primera vez)"
  if [ -f "$HOME/config.json" ]; then
    cp "$HOME/config.json" "$APP/config.json"
    ok "Usé el config.json que estaba en tu carpeta personal"
    return
  fi
  local pin=""
  while ! [[ "$pin" =~ ^[0-9]{6,}$ ]]; do
    read -r -p "    PIN para la pantalla del local (6 números o más): " pin
  done
  read -r -p "    Banco [BROU]: " banco; banco=${banco:-BROU}
  read -r -p "    Tipo de cuenta [Caja de ahorro en pesos]: " tipo; tipo=${tipo:-Caja de ahorro en pesos}
  read -r -p "    Número de cuenta: " numero
  read -r -p "    Número para transferir desde otros bancos: " otros
  read -r -p "    Titular: " titular
  PIN="$pin" BANCO="$banco" TIPO="$tipo" NUMERO="$numero" OTROS="$otros" TITULAR="$titular" \
  python3 - "$APP" <<'EOF'
import json, os, sys
app = sys.argv[1]
c = json.load(open(os.path.join(app, "config.ejemplo.json"), encoding="utf-8"))
c["pin_local"] = os.environ["PIN"]
c["banco"] = {"banco": os.environ["BANCO"], "tipo": os.environ["TIPO"], "numero": os.environ["NUMERO"],
              "numero_otros_bancos": os.environ["OTROS"], "titular": os.environ["TITULAR"]}
c["puerto"] = 8080
c["escuchar"] = "127.0.0.1"
json.dump(c, open(os.path.join(app, "config.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
EOF
  chmod 600 "$APP/config.json"
  ok "config.json creado (el horario y el envío se cambian editando ese archivo)"
}

servicio() {
  paso "Dejando el servidor como servicio"
  sudo tee /etc/systemd/system/arepalandia-pedidos.service >/dev/null <<EOF
[Unit]
Description=Pedidos Arepalandia
After=network-online.target
Wants=network-online.target

[Service]
User=$USUARIO
WorkingDirectory=$APP
Environment=PUERTO=$PUERTO
Environment=TZ=America/Montevideo
ExecStart=/usr/bin/python3 $APP/servidor.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable -q --now arepalandia-pedidos
  sudo systemctl restart arepalandia-pedidos
  sleep 2
  if curl -fsS "http://127.0.0.1:$PUERTO/api/menu" >/dev/null; then
    ok "Servidor andando en http://127.0.0.1:$PUERTO (en esta compu)"
  else
    echo "    El servidor no respondió. Mirá el error con: journalctl -u arepalandia-pedidos -n 50"
    exit 1
  fi
}

respaldo() {
  paso "Copia de seguridad diaria (23:30)"
  mkdir -p "$HOME/respaldos"
  cat > "$HOME/respaldar-arepalandia.sh" <<EOF
#!/usr/bin/env bash
# Copia la base de datos y los comprobantes. Guarda 30 días.
set -e
D="\$HOME/respaldos/\$(date +%Y-%m-%d)"
mkdir -p "\$D"
python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \\
  "$APP/datos/arepalandia.db" "\$D/arepalandia.db"
[ -d "$APP/datos/comprobantes" ] && tar -czf "\$D/comprobantes.tar.gz" -C "$APP/datos" comprobantes
cp "$APP/config.json" "\$D/config.json"
find "\$HOME/respaldos" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
EOF
  chmod +x "$HOME/respaldar-arepalandia.sh"
  ( crontab -l 2>/dev/null | grep -v respaldar-arepalandia; echo "30 23 * * * $HOME/respaldar-arepalandia.sh" ) | crontab -
  ok "Se guarda en ~/respaldos todos los días a las 23:30"
}

sin_suspender() {
  paso "Evitando que la compu se suspenda"
  sudo systemctl mask -q sleep.target suspend.target hibernate.target hybrid-sleep.target || true
  if command -v gsettings >/dev/null; then
    gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
    gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
  fi
  ok "Listo. Recordá en la BIOS: 'Restore on AC power loss' = On, para que prenda sola si vuelve la luz"
}

cloudflared_instalar() {
  if command -v cloudflared >/dev/null; then return; fi
  paso "Instalando Cloudflare (túnel)"
  sudo mkdir -p --mode=0755 /usr/share/keyrings
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  sudo apt-get update -qq && sudo apt-get install -y -qq cloudflared >/dev/null
  ok "cloudflared instalado"
}

tunel() {
  local dominio="$1"
  cloudflared_instalar
  paso "Conectando $dominio"
  echo "    Se abre el navegador: entrá a tu cuenta de Cloudflare y elegí el dominio."
  [ -f "$HOME/.cloudflared/cert.pem" ] || cloudflared tunnel login
  cloudflared tunnel list 2>/dev/null | grep -q " arepalandia " || cloudflared tunnel create arepalandia
  local id
  id=$(cloudflared tunnel list | awk '$2=="arepalandia"{print $1}')
  cloudflared tunnel route dns arepalandia "$dominio" || true
  sudo mkdir -p /etc/cloudflared
  sudo cp "$HOME/.cloudflared/$id.json" /etc/cloudflared/
  sudo tee /etc/cloudflared/config.yml >/dev/null <<EOF
tunnel: $id
credentials-file: /etc/cloudflared/$id.json
ingress:
  - hostname: $dominio
    service: http://127.0.0.1:$PUERTO
  - service: http_status:404
EOF
  sudo cloudflared service install 2>/dev/null || sudo systemctl restart cloudflared
  ok "Listo: https://$dominio para los clientes y https://$dominio/local para el local"
}

tunel_prueba() {
  cloudflared_instalar
  paso "Link de prueba (cambia cada vez que se reinicia; para probar hasta tener el dominio)"
  echo "    Copiá el link que termina en trycloudflare.com. Cortá con Ctrl+C."
  cloudflared tunnel --url "http://127.0.0.1:$PUERTO"
}

case "${1:-}" in
  tunel)
    [ -n "${2:-}" ] || { echo "Uso: bash instalar.sh tunel pedidos.midominio.com"; exit 1; }
    tunel "$2" ;;
  prueba)
    tunel_prueba ;;
  *)
    instalar_base
    configurar
    servicio
    respaldo
    sin_suspender
    paso "Todo listo"
    echo "    - Para probar desde internet ya:   bash instalar.sh prueba"
    echo "    - Cuando tengan el dominio:        bash instalar.sh tunel pedidos.midominio.com"
    echo "    - Para actualizar en el futuro:    bash instalar.sh"
    ;;
esac
