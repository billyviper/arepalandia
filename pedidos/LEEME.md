# Pedidos Arepalandia

Página de pedidos para clientes y pantalla del local (pedidos, mostrador, stock y ventas).
Solo necesita Python 3, que ya viene en Linux.

## Probar

```
cd pedidos
python3 servidor.py
```

- Clientes: http://localhost:8080
- Local: http://localhost:8080/local (pide el PIN de `config.json`)

## Configurar

`config.json` tiene los datos del banco, el costo del envío y el PIN del local.
No se sube a GitHub (el repositorio es público). Si no existe, se crea solo a partir de `config.ejemplo.json`.

Los pedidos, clientes y comprobantes quedan en la carpeta `datos/`. Esa carpeta es la que hay que copiar todos los días como respaldo.

## Cómo queda armado

```
Clientes (celular) ──► https://pedidos.<dominio> ──► túnel de Cloudflare ──► Servidor en casa (esta carpeta)
                                                                               ▲
Compu del local + impresora ── navegador en /local (PIN) ──────────────────────┘
```

- **Servidor en casa** (la compu de 15", Linux): corre `servidor.py` todo el día, guarda pedidos, clientes y comprobantes en `datos/`. Escucha solo en `127.0.0.1`; el túnel de Cloudflare es la única entrada desde internet.
- **Compu del local**: solo abre `https://pedidos.<dominio>/local` en Chrome en modo kiosco con impresión directa (`--kiosk --kiosk-printing`). No guarda nada: si se corta internet aparece una franja roja, y los pedidos que entraron mientras tanto se imprimen apenas vuelve la conexión (no se repiten, la pantalla recuerda cuáles ya imprimió).
- **Horario**: fuera de los turnos de `config.json` (`turnos`, 0 = lunes) la página muestra "Ahora estamos cerrados" y no acepta pedidos. `solo_en_horario: false` lo desactiva.
- **PIN**: 5 intentos fallidos desde la misma dirección bloquean 15 minutos. Usar un PIN de 6 dígitos o más.

## Pendiente para instalar en la compu

- Servidor en casa: arranque automático (servicio de systemd), BIOS en "encender al volver la luz", y que no se suspenda.
- Compu del local: acceso directo a Chrome en modo kiosco con `--kiosk-printing` apuntando a `/local`.
- Acceso desde internet con un túnel de Cloudflare.
- Impresora térmica de 80 mm como impresora del sistema; el ticket se imprime desde el navegador.
- Copia diaria de `datos/` a Google Drive.
