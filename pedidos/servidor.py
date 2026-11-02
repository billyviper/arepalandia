#!/usr/bin/env python3
"""Servidor de pedidos de Arepalandia.

Solo usa Python 3 (sin instalar nada más). Arranca con:
    python3 servidor.py
y queda escuchando en http://localhost:8080

- /            página de pedidos para clientes
- /local       pantalla del local (pide el PIN de config.json)
"""
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(BASE, "datos")
COMPROBANTES = os.path.join(DATOS, "comprobantes")
WEB = os.path.join(BASE, "web")
os.makedirs(COMPROBANTES, exist_ok=True)

if not os.path.exists(os.path.join(BASE, "config.json")):
    import shutil
    shutil.copy(os.path.join(BASE, "config.ejemplo.json"), os.path.join(BASE, "config.json"))
    print("Creé config.json desde el ejemplo: completá los datos del banco y cambiá el PIN.")
with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)

# Turnos de atención: 0 = lunes … 6 = domingo. Fuera de estos turnos la página no acepta pedidos.
TURNOS_DEFECTO = {"0": [], "1": [["10:00", "13:00"], ["20:00", "23:00"]], "2": [["10:00", "13:00"], ["20:00", "23:00"]],
                  "3": [["10:00", "13:00"], ["20:00", "23:00"]], "4": [["10:00", "13:00"], ["20:00", "23:00"]],
                  "5": [["20:00", "23:00"]], "6": [["20:00", "23:00"]]}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
try:
    from zoneinfo import ZoneInfo
    ZONA = ZoneInfo(CONFIG.get("zona_horaria", "America/Montevideo"))
except Exception:  # sin base de zonas: hora de la máquina
    ZONA = None


def ahora_local():
    return datetime.now(ZONA) if ZONA else datetime.now()


def estado_atencion(momento=None):
    """Devuelve (abierto, texto) según los turnos de config.json."""
    turnos = CONFIG.get("turnos") or TURNOS_DEFECTO
    t = momento or ahora_local()
    hhmm = t.strftime("%H:%M")
    for ini, fin in turnos.get(str(t.weekday()), []):
        if ini <= hhmm < fin:
            return True, f"Abierto hasta las {fin}"
    for extra in range(0, 8):  # próxima apertura
        dia = (t.weekday() + extra) % 7
        for ini, fin in turnos.get(str(dia), []):
            if extra == 0 and ini <= hhmm:
                continue
            cuando = "hoy" if extra == 0 else ("mañana" if extra == 1 else "el " + DIAS[dia])
            return False, f"Ahora estamos cerrados. Abrimos {cuando} a las {ini}."
    return False, "Ahora estamos cerrados."


# Intentos de PIN fallidos por dirección: después de 5 en 15 minutos se bloquea 15 minutos.
INTENTOS = {}
MAX_INTENTOS, VENTANA_INTENTOS = 5, 15 * 60

DB_PATH = os.path.join(DATOS, "arepalandia.db")
LOCK = threading.Lock()
MAX_COMPROBANTE = 8 * 1024 * 1024
TIPOS_COMPROBANTE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                     "image/heic": ".heic", "application/pdf": ".pdf"}
ESTADOS = ["nuevo", "pago verificado", "en preparación", "enviado", "entregado", "cancelado"]


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def iniciar_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS productos (
            numero INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            detalle TEXT,
            categoria TEXT,
            precio INTEGER NOT NULL,
            opciones TEXT,
            stock INTEGER,              -- NULL = sin control de stock
            activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telefono TEXT UNIQUE,
            nombre TEXT NOT NULL,
            cumple TEXT,
            acepta_datos INTEGER NOT NULL DEFAULT 0,
            creado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creado TEXT NOT NULL,
            canal TEXT NOT NULL,         -- web / mostrador
            origen TEXT,                 -- cómo nos conoció / link
            cliente_id INTEGER REFERENCES clientes(id),
            nombre TEXT NOT NULL,
            telefono TEXT,
            entrega TEXT NOT NULL,       -- delivery / retiro / mostrador
            direccion TEXT,
            nota TEXT,
            pago TEXT NOT NULL,          -- efectivo / transferencia
            paga_con INTEGER,
            cambio INTEGER,
            comprobante TEXT,
            subtotal INTEGER NOT NULL,
            envio INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL,
            estado TEXT NOT NULL DEFAULT 'nuevo',
            actualizado TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
            numero INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            opcion TEXT,
            cantidad INTEGER NOT NULL,
            precio INTEGER NOT NULL,
            importe INTEGER NOT NULL
        );
        """)
        if con.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
            with open(os.path.join(BASE, "menu.json"), encoding="utf-8") as f:
                for p in json.load(f):
                    con.execute(
                        "INSERT INTO productos (numero,nombre,detalle,categoria,precio,opciones,stock) VALUES (?,?,?,?,?,?,?)",
                        (p["numero"], p["nombre"], p.get("detalle", ""), p["categoria"], p["precio"],
                         json.dumps(p.get("opciones", []), ensure_ascii=False), p.get("stock")))
        else:
            # Si se agregan opciones nuevas en menu.json (p. ej. sabores), se copian a la base.
            with open(os.path.join(BASE, "menu.json"), encoding="utf-8") as f:
                for p in json.load(f):
                    con.execute("UPDATE productos SET opciones = ? WHERE numero = ?",
                                (json.dumps(p.get("opciones", []), ensure_ascii=False), p["numero"]))


def ahora():
    return ahora_local().replace(tzinfo=None).isoformat(timespec="seconds")


def menu(con, todo=False):
    q = "SELECT * FROM productos" + ("" if todo else " WHERE activo = 1") + " ORDER BY numero"
    out = []
    for r in con.execute(q):
        d = dict(r)
        d["opciones"] = json.loads(d["opciones"] or "[]")
        out.append(d)
    return out


def limpiar(texto, largo=200):
    return re.sub(r"\s+", " ", str(texto or "")).strip()[:largo]


class ErrorPedido(Exception):
    pass


def crear_pedido(datos, comprobante=None, canal="web"):
    """Valida, calcula el total en el servidor, descuenta stock y guarda."""
    if canal == "web" and CONFIG.get("solo_en_horario", True):
        abierto, texto = estado_atencion()
        if not abierto:
            raise ErrorPedido(texto)
    items = datos.get("items") or []
    if not items:
        raise ErrorPedido("El pedido está vacío.")
    nombre = limpiar(datos.get("nombre"), 60)
    if not nombre and canal == "web":
        raise ErrorPedido("Falta el nombre.")
    telefono = re.sub(r"[^0-9+]", "", str(datos.get("telefono") or ""))[:20]
    if canal == "web" and len(re.sub(r"\D", "", telefono)) < 8:
        raise ErrorPedido("Falta un teléfono válido.")
    entrega = datos.get("entrega") if canal == "web" else "mostrador"
    if entrega not in ("delivery", "retiro", "mostrador"):
        raise ErrorPedido("Elegí delivery o retiro.")
    direccion = limpiar(datos.get("direccion"), 160)
    if entrega == "delivery" and not direccion:
        raise ErrorPedido("Falta la dirección.")
    pago = datos.get("pago")
    if pago not in ("efectivo", "transferencia"):
        raise ErrorPedido("Elegí cómo pagás.")
    if canal == "web" and pago == "transferencia" and not comprobante:
        raise ErrorPedido("Subí el comprobante de la transferencia.")
    cumple = str(datos.get("cumple") or "")
    if cumple and not re.fullmatch(r"\d{2}-\d{2}", cumple):
        raise ErrorPedido("El cumpleaños va como día y mes.")
    acepta = bool(datos.get("acepta_datos"))

    with LOCK, db() as con:
        productos = {p["numero"]: p for p in menu(con)}
        lineas, subtotal, pedidos_por_numero = [], 0, {}
        for it in items:
            try:
                num, cant = int(it.get("numero")), int(it.get("cantidad"))
            except (TypeError, ValueError):
                raise ErrorPedido("Hay un producto mal cargado.")
            if num not in productos or not 1 <= cant <= 50:
                raise ErrorPedido("Hay un producto que ya no está en el menú.")
            p = productos[num]
            opcion = limpiar(it.get("opcion"), 40)
            if p["opciones"] and opcion not in p["opciones"]:
                raise ErrorPedido(f"Elegí el {'sabor' if p['categoria'] == 'Bebidas' else 'relleno'} de {p['nombre']}.")
            pedidos_por_numero[num] = pedidos_por_numero.get(num, 0) + cant
            importe = p["precio"] * cant
            subtotal += importe
            lineas.append((num, p["nombre"], opcion or None, cant, p["precio"], importe))
        for num, cant in pedidos_por_numero.items():
            st = productos[num]["stock"]
            if st is not None and cant > st:
                quedan = f"quedan {st}" if st > 0 else "está agotado"
                raise ErrorPedido(f"{productos[num]['nombre']}: {quedan}.")

        envio = 0
        if entrega == "delivery" and subtotal < int(CONFIG["envio_gratis_desde"]):
            envio = int(CONFIG["envio_costo"])
        total = subtotal + envio
        paga_con = cambio = None
        if pago == "efectivo" and canal == "web" and entrega == "delivery":
            try:
                paga_con = int(datos.get("paga_con") or total)
            except ValueError:
                raise ErrorPedido("Poné con cuánto pagás.")
            if paga_con < total:
                raise ErrorPedido(f"El total es ${total}: poné un monto igual o mayor.")
            cambio = paga_con - total

        cliente_id = None
        if telefono and acepta:
            fila = con.execute("SELECT id FROM clientes WHERE telefono = ?", (telefono,)).fetchone()
            if fila:
                cliente_id = fila["id"]
                con.execute("UPDATE clientes SET nombre = ?, cumple = COALESCE(NULLIF(?, ''), cumple), acepta_datos = 1 WHERE id = ?",
                            (nombre, cumple, cliente_id))
            else:
                cliente_id = con.execute(
                    "INSERT INTO clientes (telefono,nombre,cumple,acepta_datos,creado) VALUES (?,?,?,1,?)",
                    (telefono, nombre, cumple or None, ahora())).lastrowid

        archivo = None
        if comprobante:
            archivo = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(4)}{comprobante[1]}"
            with open(os.path.join(COMPROBANTES, archivo), "wb") as f:
                f.write(comprobante[0])

        estado = "entregado" if canal == "mostrador" else "nuevo"
        t = ahora()
        pid = con.execute(
            """INSERT INTO pedidos (creado,canal,origen,cliente_id,nombre,telefono,entrega,direccion,nota,pago,
               paga_con,cambio,comprobante,subtotal,envio,total,estado,actualizado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t, canal, limpiar(datos.get("origen"), 60), cliente_id, nombre or "Mostrador", telefono or None,
             entrega, direccion or None, limpiar(datos.get("nota"), 200), pago, paga_con, cambio, archivo,
             subtotal, envio, total, estado, t)).lastrowid
        for ln in lineas:
            con.execute("INSERT INTO items (pedido_id,numero,nombre,opcion,cantidad,precio,importe) VALUES (?,?,?,?,?,?,?)",
                        (pid, *ln))
        for num, cant in pedidos_por_numero.items():
            if productos[num]["stock"] is not None:
                con.execute("UPDATE productos SET stock = stock - ? WHERE numero = ?", (cant, num))
        return pedido_completo(con, pid)


def pedido_completo(con, pid):
    p = con.execute("SELECT * FROM pedidos WHERE id = ?", (pid,)).fetchone()
    if not p:
        return None
    d = dict(p)
    d["items"] = [dict(r) for r in con.execute("SELECT * FROM items WHERE pedido_id = ? ORDER BY id", (pid,))]
    return d


def mensaje_whatsapp(p):
    lineas = [f"Hola Arepalandia, soy {p['nombre']}. Pedido #{p['id']}:"]
    for it in p["items"]:
        op = f" ({it['opcion']})" if it["opcion"] else ""
        lineas.append(f"- {it['cantidad']} x {it['nombre']}{op}: ${it['importe']}")
    if p["envio"]:
        lineas.append(f"- Envío: ${p['envio']}")
    lineas.append(f"Total: ${p['total']}")
    if p["entrega"] == "delivery":
        lineas.append(f"Delivery a: {p['direccion']}")
    else:
        lineas.append("Lo retiro en el local")
    if p["pago"] == "efectivo":
        extra = f", pago con ${p['paga_con']} (cambio ${p['cambio']})" if p["paga_con"] else ""
        lineas.append(f"Pago en efectivo{extra}")
    else:
        lineas.append("Pagué por transferencia, ya subí el comprobante")
    return "\n".join(lineas)


def leer_multipart(handler, largo):
    ctype = handler.headers.get("Content-Type", "")
    cuerpo = handler.rfile.read(largo)
    msg = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + ctype.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + cuerpo)
    campos, archivo = {}, None
    for parte in msg.iter_parts():
        nombre = parte.get_param("name", header="content-disposition")
        if parte.get_filename():
            data = parte.get_payload(decode=True) or b""
            if data:
                archivo = (data, parte.get_content_type())
        else:
            campos[nombre] = (parte.get_payload(decode=True) or b"").decode("utf-8", "replace")
    return campos, archivo


class Handler(BaseHTTPRequestHandler):
    server_version = "Arepalandia"

    def log_message(self, fmt, *args):
        pass

    # ---- respuestas ----
    def json(self, data, code=200):
        cuerpo = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def archivo(self, ruta, tipo):
        try:
            with open(ruta, "rb") as f:
                cuerpo = f.read()
        except FileNotFoundError:
            return self.json({"error": "No existe"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def ip(self):
        # Detrás del túnel de Cloudflare la dirección real viene en este encabezado.
        return self.headers.get("CF-Connecting-IP") or self.client_address[0]

    def bloqueado(self):
        ahora = time.time()
        fallas = [t for t in INTENTOS.get(self.ip(), []) if ahora - t < VENTANA_INTENTOS]
        INTENTOS[self.ip()] = fallas
        return len(fallas) >= MAX_INTENTOS

    def autorizado(self):
        if self.bloqueado():
            return False
        ok = secrets.compare_digest(self.headers.get("X-Pin", ""), str(CONFIG["pin_local"]))
        if not ok:
            INTENTOS.setdefault(self.ip(), []).append(time.time())
        return ok

    def rechazo_pin(self):
        if self.bloqueado():
            return self.json({"error": "Demasiados intentos. Probá de nuevo en 15 minutos."}, 429)
        return self.json({"error": "PIN incorrecto"}, 401)

    def cuerpo_json(self):
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > 200_000:
            raise ErrorPedido("Pedido demasiado grande.")
        return json.loads(self.rfile.read(largo) or b"{}")

    # ---- GET ----
    def do_GET(self):
        url = urlparse(self.path)
        ruta = url.path
        if ruta in ("/", "/pedir"):
            return self.archivo(os.path.join(WEB, "pedir.html"), "text/html; charset=utf-8")
        if ruta == "/local":
            return self.archivo(os.path.join(WEB, "local.html"), "text/html; charset=utf-8")
        if ruta == "/api/menu":
            with db() as con:
                return self.json({"negocio": publico(), "productos": menu(con)})
        if ruta.startswith("/api/local/"):
            if not self.autorizado():
                return self.rechazo_pin()
            return self.get_local(ruta, parse_qs(url.query))
        return self.json({"error": "No existe"}, 404)

    def get_local(self, ruta, q):
        with db() as con:
            if ruta == "/api/local/pedidos":
                dia = (q.get("dia") or [ahora_local().strftime("%Y-%m-%d")])[0]
                ids = [r[0] for r in con.execute("SELECT id FROM pedidos WHERE creado LIKE ? ORDER BY id DESC", (dia + "%",))]
                return self.json({"pedidos": [pedido_completo(con, i) for i in ids], "estados": ESTADOS})
            if ruta == "/api/local/productos":
                return self.json({"productos": menu(con, todo=True)})
            m = re.fullmatch(r"/api/local/comprobante/(\d+)", ruta)
            if m:
                p = con.execute("SELECT comprobante FROM pedidos WHERE id = ?", (int(m.group(1)),)).fetchone()
                if not p or not p["comprobante"]:
                    return self.json({"error": "Sin comprobante"}, 404)
                ext = os.path.splitext(p["comprobante"])[1]
                tipo = {v: k for k, v in TIPOS_COMPROBANTE.items()}.get(ext, "application/octet-stream")
                return self.archivo(os.path.join(COMPROBANTES, p["comprobante"]), tipo)
            if ruta == "/api/local/ventas.csv":
                filas = ["fecha,hora,pedido,canal,entrega,cliente,producto,opcion,cantidad,precio,importe,pago,estado"]
                for r in con.execute("""SELECT p.creado,p.id,p.canal,p.entrega,p.nombre,i.nombre AS prod,i.opcion,
                        i.cantidad,i.precio,i.importe,p.pago,p.estado FROM items i JOIN pedidos p ON p.id = i.pedido_id
                        WHERE p.estado != 'cancelado' ORDER BY p.id"""):
                    fecha, hora = r["creado"].split("T")
                    celdas = [fecha, hora, r["id"], r["canal"], r["entrega"], r["nombre"], r["prod"], r["opcion"] or "",
                              r["cantidad"], r["precio"], r["importe"], r["pago"], r["estado"]]
                    filas.append(",".join('"' + str(c).replace('"', '""') + '"' for c in celdas))
                cuerpo = ("﻿" + "\n".join(filas)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", "attachment; filename=ventas-arepalandia.csv")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
                return
        return self.json({"error": "No existe"}, 404)

    # ---- POST ----
    def do_POST(self):
        ruta = urlparse(self.path).path
        try:
            if ruta == "/api/pedidos":
                largo = int(self.headers.get("Content-Length") or 0)
                if largo > MAX_COMPROBANTE + 200_000:
                    raise ErrorPedido("El comprobante es muy pesado (máximo 8 MB).")
                if self.headers.get("Content-Type", "").startswith("multipart/form-data"):
                    campos, archivo = leer_multipart(self, largo)
                    datos = json.loads(campos.get("pedido") or "{}")
                else:
                    datos, archivo = json.loads(self.rfile.read(largo) or b"{}"), None
                comp = None
                if archivo:
                    if archivo[1] not in TIPOS_COMPROBANTE:
                        raise ErrorPedido("El comprobante tiene que ser foto o PDF.")
                    comp = (archivo[0], TIPOS_COMPROBANTE[archivo[1]])
                p = crear_pedido(datos, comp, "web")
                return self.json({"pedido": p, "whatsapp": CONFIG["whatsapp"], "mensaje": mensaje_whatsapp(p)})
            if not ruta.startswith("/api/local/"):
                return self.json({"error": "No existe"}, 404)
            if not self.autorizado():
                return self.rechazo_pin()
            datos = self.cuerpo_json()
            if ruta == "/api/local/mostrador":
                return self.json({"pedido": crear_pedido(datos, None, "mostrador")})
            if ruta == "/api/local/estado":
                if datos.get("estado") not in ESTADOS:
                    raise ErrorPedido("Estado desconocido.")
                with LOCK, db() as con:
                    p = con.execute("SELECT estado FROM pedidos WHERE id = ?", (int(datos["id"]),)).fetchone()
                    if not p:
                        raise ErrorPedido("No existe ese pedido.")
                    if datos["estado"] == "cancelado" and p["estado"] != "cancelado":
                        for it in con.execute("SELECT numero, cantidad FROM items WHERE pedido_id = ?", (int(datos["id"]),)):
                            con.execute("UPDATE productos SET stock = stock + ? WHERE numero = ? AND stock IS NOT NULL",
                                        (it["cantidad"], it["numero"]))
                    con.execute("UPDATE pedidos SET estado = ?, actualizado = ? WHERE id = ?",
                                (datos["estado"], ahora(), int(datos["id"])))
                    return self.json({"pedido": pedido_completo(con, int(datos["id"]))})
            if ruta == "/api/local/producto":
                with LOCK, db() as con:
                    num = int(datos["numero"])
                    if "stock" in datos:
                        st = datos["stock"]
                        con.execute("UPDATE productos SET stock = ? WHERE numero = ?",
                                    (None if st in (None, "") else max(0, int(st)), num))
                    if "activo" in datos:
                        con.execute("UPDATE productos SET activo = ? WHERE numero = ?", (1 if datos["activo"] else 0, num))
                    if "precio" in datos:
                        con.execute("UPDATE productos SET precio = ? WHERE numero = ?", (max(0, int(datos["precio"])), num))
                    return self.json({"productos": menu(con, todo=True)})
            return self.json({"error": "No existe"}, 404)
        except ErrorPedido as e:
            return self.json({"error": str(e)}, 400)
        except (ValueError, KeyError, json.JSONDecodeError):
            return self.json({"error": "Datos mal enviados."}, 400)


def publico():
    claves = ["nombre", "whatsapp", "envio_costo", "envio_gratis_desde", "banco", "horario"]
    d = {k: CONFIG[k] for k in claves}
    d["abierto"], d["atencion"] = estado_atencion()
    if not CONFIG.get("solo_en_horario", True):
        d["abierto"] = True
    return d


if __name__ == "__main__":
    iniciar_db()
    puerto = int(os.environ.get("PUERTO", CONFIG.get("puerto", 8080)))
    print(f"Arepalandia pedidos en http://localhost:{puerto}  (local: /local)")
    ThreadingHTTPServer((os.environ.get("HOST") or CONFIG.get("escuchar", "127.0.0.1"), puerto), Handler).serve_forever()
