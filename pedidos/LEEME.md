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

## Pendiente para instalar en la compu

- Arranque automático al prender la compu (servicio de systemd).
- Acceso desde internet con un túnel de Cloudflare.
- Impresora térmica de 80 mm como impresora del sistema; el ticket se imprime desde el navegador.
- Copia diaria de `datos/` a Google Drive.
