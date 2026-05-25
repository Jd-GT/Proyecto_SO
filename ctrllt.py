# ctrllt.py — Servicio de Control de Lotes
#
# PROPÓSITO:
#   Es la pasarela central del sistema. Recibe peticiones del cliente,
#   las redirige al servicio correcto (gesfich, gesprog, ejecutor),
#   espera la respuesta y la reenvía al cliente.
#   No procesa ni modifica los mensajes — solo los redirige.
#
# USO:
#   python3 ctrllt.py
#       -c <tuberia-peticiones-cliente> [-a <tuberia-respuestas-cliente>]
#       -f <tuberia-peticiones-gesfich> [-b <tuberia-respuestas-gesfich>]
#       -p <tuberia-peticiones-gesprog> [-g <tuberia-respuestas-gesprog>]
#       -e <tuberia-peticiones-ejecutor> [-d <tuberia-respuestas-ejecutor>]
#
# NOTA SOBRE LOS FLAGS:
#   El PDF original tiene un error tipográfico: repite -c dos veces.
#   Usamos -g para las respuestas de gesprog en lugar de -c.
#
# EJEMPLO:
#   python3 ctrllt.py \
#     -c /tmp/cliente_req -a /tmp/cliente_res \
#     -f /tmp/gesfich_req -b /tmp/gesfich_res \
#     -p /tmp/gesprog_req -g /tmp/gesprog_res \
#     -e /tmp/ejecutor_req -d /tmp/ejecutor_res

# ─────────────────────────────────────────────
# IMPORTACIONES
# ─────────────────────────────────────────────

import sys
# sys.argv   → argumentos de línea de comandos
# sys.stderr → salida de errores
# sys.exit() → terminar el programa

import ipc
# Nuestro módulo de comunicación por tuberías nombradas


# ─────────────────────────────────────────────
# FUNCIÓN: abrir_tuberias_servicios
# ─────────────────────────────────────────────

def abrir_tuberias_servicios(rutas):
    """
    PROPÓSITO:
        Abre las tuberías de comunicación con los servicios internos
        (gesfich, gesprog, ejecutor).

        Para cada servicio, ctrllt:
        - ESCRIBE en la tubería de peticiones (envía pedidos al servicio)
        - LEE de la tubería de respuestas (recibe respuestas del servicio)

    PARÁMETRO:
        rutas (dict): Diccionario con las rutas de las tuberías.
            {
                "gesfich_req": "/tmp/gesfich_req",
                "gesfich_res": "/tmp/gesfich_res",
                ...
            }

    RETORNA:
        Un diccionario con los file descriptors abiertos.
        None si alguna tubería falló al abrirse.

    ORDEN DE APERTURA — MUY IMPORTANTE:
        Los servicios ya están corriendo y esperando con sus tuberías
        abiertas para LEER (tubería de peticiones).
        ctrllt debe abrir para ESCRIBIR primero → desbloquea al servicio.
        Luego abre para LEER (tubería de respuestas).
        El servicio abrirá para ESCRIBIR su respuesta → ctrllt se desbloquea.

        Si abrimos en orden incorrecto → deadlock.
    """

    fds = {}

    print("[ctrllt] Conectando con gesfich...", file=sys.stderr)

    # ── gesfich ──
    # Primero abrimos para ESCRIBIR (peticiones) → desbloquea a gesfich
    fds["gesfich_req"] = ipc.abrir_tuberia_escritura(rutas["gesfich_req"])
    if fds["gesfich_req"] is None:
        print("[ctrllt] Error conectando con gesfich (req)", file=sys.stderr)
        return None

    # Luego abrimos para LEER (respuestas) → gesfich abre su lado
    fds["gesfich_res"] = ipc.abrir_tuberia_lectura(rutas["gesfich_res"])
    if fds["gesfich_res"] is None:
        print("[ctrllt] Error conectando con gesfich (res)", file=sys.stderr)
        return None

    print("[ctrllt] Conectado con gesfich ✓", file=sys.stderr)
    print("[ctrllt] Conectando con gesprog...", file=sys.stderr)

    # ── gesprog ──
    fds["gesprog_req"] = ipc.abrir_tuberia_escritura(rutas["gesprog_req"])
    if fds["gesprog_req"] is None:
        print("[ctrllt] Error conectando con gesprog (req)", file=sys.stderr)
        return None

    fds["gesprog_res"] = ipc.abrir_tuberia_lectura(rutas["gesprog_res"])
    if fds["gesprog_res"] is None:
        print("[ctrllt] Error conectando con gesprog (res)", file=sys.stderr)
        return None

    print("[ctrllt] Conectado con gesprog ✓", file=sys.stderr)
    print("[ctrllt] Conectando con ejecutor...", file=sys.stderr)

    # ── ejecutor ──
    fds["ejecutor_req"] = ipc.abrir_tuberia_escritura(rutas["ejecutor_req"])
    if fds["ejecutor_req"] is None:
        print("[ctrllt] Error conectando con ejecutor (req)", file=sys.stderr)
        return None

    fds["ejecutor_res"] = ipc.abrir_tuberia_lectura(rutas["ejecutor_res"])
    if fds["ejecutor_res"] is None:
        print("[ctrllt] Error conectando con ejecutor (res)", file=sys.stderr)
        return None

    print("[ctrllt] Conectado con ejecutor ✓", file=sys.stderr)

    return fds


# ─────────────────────────────────────────────
# FUNCIÓN: suspender_servicios
# ─────────────────────────────────────────────

def suspender_servicios(fds):
    """
    PROPÓSITO:
        Envía la operación "Suspender" a todos los servicios activos.
        Se llama cuando ctrllt recibe la operación "Terminar".

        El profe dijo: "cuando control recibe terminar y hay servicios
        corriendo los debe suspender".

    PARÁMETRO:
        fds (dict): Diccionario con los file descriptors abiertos.

    POR QUÉ SUSPENDER Y NO TERMINAR:
        Suspender permite que los lotes activos en el ejecutor
        continúen corriendo. Terminar los mataría abruptamente.
        El profe especificó suspender, no terminar.
    """

    mensaje_suspender = {
        "operacion": "Suspender",
        "parametros": {}
    }

    servicios = [
        ("gesfich", fds.get("gesfich_req"), fds.get("gesfich_res")),
        ("gesprog", fds.get("gesprog_req"), fds.get("gesprog_res")),
        ("ejecutor", fds.get("ejecutor_req"), fds.get("ejecutor_res")),
    ]

    # Recorremos cada servicio y le enviamos Suspender.
    # Esperamos su respuesta para confirmar que la recibió.
    for nombre, fd_req, fd_res in servicios:
        if fd_req is not None and fd_res is not None:
            print(f"[ctrllt] Suspendiendo {nombre}...", file=sys.stderr)
            ipc.enviar_mensaje(fd_req, mensaje_suspender)
            respuesta = ipc.recibir_mensaje(fd_res)
            if respuesta:
                print(f"[ctrllt] {nombre} respondió: {respuesta}", file=sys.stderr)


# ─────────────────────────────────────────────
# FUNCIÓN: redirigir_peticion
# ─────────────────────────────────────────────

def redirigir_peticion(mensaje, fds):
    """
    PROPÓSITO:
        Lee el campo "servicio" del mensaje del cliente,
        reenvía el mensaje al servicio correspondiente,
        espera la respuesta y la retorna.

    PARÁMETROS:
        mensaje (dict): El mensaje completo recibido del cliente.
        fds     (dict): Diccionario con los file descriptors abiertos.

    RETORNA:
        La respuesta del servicio como diccionario.
        O un dict de error si el servicio es desconocido.

    POR QUÉ NO MODIFICAMOS EL MENSAJE:
        ctrllt es una pasarela ciega. El profe dijo:
        "control solo recibe y redirige".
        No agregamos ni quitamos campos — enviamos exactamente
        lo que recibimos del cliente al servicio.
    """

    # Extraemos el campo "servicio" para saber a dónde redirigir.
    servicio = mensaje.get("servicio", "")

    # Diccionario que mapea nombre del servicio a sus file descriptors.
    # fd_req → donde enviamos la petición
    # fd_res → donde leemos la respuesta
    mapa_servicios = {
        "gesfich": (fds.get("gesfich_req"), fds.get("gesfich_res")),
        "gesprog": (fds.get("gesprog_req"), fds.get("gesprog_res")),
        "ejecutor": (fds.get("ejecutor_req"), fds.get("ejecutor_res")),
    }

    if servicio not in mapa_servicios:
        # Servicio desconocido — retornamos error sin redirigir nada.
        return {
            "estado": "error",
            "mensaje": f"Servicio desconocido: {servicio}"
        }

    fd_req, fd_res = mapa_servicios[servicio]

    if fd_req is None or fd_res is None:
        return {
            "estado": "error",
            "mensaje": f"Servicio {servicio} no está conectado"
        }

    # Enviamos el mensaje completo al servicio.
    # El servicio leerá los campos "operacion" y "parametros"
    # directamente — no necesita el campo "servicio".
    exito = ipc.enviar_mensaje(fd_req, mensaje)

    if not exito:
        return {
            "estado": "error",
            "mensaje": f"Error al enviar mensaje a {servicio}"
        }

    # Esperamos la respuesta del servicio.
    # recibir_mensaje() bloquea hasta que el servicio responda.
    respuesta = ipc.recibir_mensaje(fd_res)

    if respuesta is None:
        return {
            "estado": "error",
            "mensaje": f"Error al recibir respuesta de {servicio}"
        }

    return respuesta


# ─────────────────────────────────────────────
# FUNCIÓN: cerrar_todo
# ─────────────────────────────────────────────

def cerrar_todo(fds, rutas, fd_cliente_req, fd_cliente_res,
                tuberia_cliente_req, tuberia_cliente_res):
    """
    PROPÓSITO:
        Cierra todos los file descriptors y elimina todas
        las tuberías del disco al terminar ctrllt.

        ctrllt es responsable de crear y limpiar las tuberías
        del cliente. Las tuberías de los servicios las crean
        y limpian los propios servicios.

    POR QUÉ CTRLLT LIMPIA LAS TUBERÍAS DEL CLIENTE:
        El cliente no crea sus propias tuberías — se conecta
        a las que ctrllt crea. Por eso ctrllt es responsable
        de crearlas al inicio y eliminarlas al final.
    """

    print("[ctrllt] Cerrando conexiones con servicios...", file=sys.stderr)

    # Cerramos los file descriptors de los servicios.
    # Solo cerramos los fds — no eliminamos las tuberías porque
    # cada servicio es responsable de limpiar las suyas.
    servicios_fds = [
        "gesfich_req", "gesfich_res",
        "gesprog_req",  "gesprog_res",
        "ejecutor_req", "ejecutor_res"
    ]

    for nombre_fd in servicios_fds:
        fd = fds.get(nombre_fd)
        if fd is not None:
            try:
                fd.close()
            except OSError:
                pass
            # pass aquí significa "ignorar el error silenciosamente".
            # En la limpieza final, si un fd ya estaba cerrado,
            # no queremos que el programa explote por eso.

    # Cerramos y eliminamos las tuberías del cliente.
    # ipc.cerrar_tuberia() cierra el fd Y elimina el archivo FIFO.
    ipc.cerrar_tuberia(fd_cliente_req, tuberia_cliente_req)
    ipc.cerrar_tuberia(fd_cliente_res, tuberia_cliente_res)

    print("[ctrllt] Limpieza completada.", file=sys.stderr)


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL: main
# ─────────────────────────────────────────────

def main():
    """
    PROPÓSITO:
        Punto de entrada de ctrllt.
        1. Lee argumentos de línea de comandos.
        2. Crea las tuberías del cliente.
        3. Se conecta con los servicios (abre sus tuberías).
        4. Abre las tuberías del cliente.
        5. Entra al loop principal redirigiendo mensajes.
        6. Limpia recursos al terminar.
    """

    # ── PASO 1: Valores por defecto ──
    tuberia_cliente_req = "/tmp/cliente_req"
    tuberia_cliente_res = "/tmp/cliente_res"

    rutas = {
        "gesfich_req": "/tmp/gesfich_req",
        "gesfich_res": "/tmp/gesfich_res",
        "gesprog_req": "/tmp/gesprog_req",
        "gesprog_res": "/tmp/gesprog_res",
        "ejecutor_req": "/tmp/ejecutor_req",
        "ejecutor_res": "/tmp/ejecutor_res",
    }

    # ── PASO 2: Leer argumentos de línea de comandos ──
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] == "-c" and i + 1 < len(args):
            tuberia_cliente_req = args[i + 1]
            i += 2
        elif args[i] == "-a" and i + 1 < len(args):
            tuberia_cliente_res = args[i + 1]
            i += 2
        elif args[i] == "-f" and i + 1 < len(args):
            rutas["gesfich_req"] = args[i + 1]
            i += 2
        elif args[i] == "-b" and i + 1 < len(args):
            rutas["gesfich_res"] = args[i + 1]
            i += 2
        elif args[i] == "-p" and i + 1 < len(args):
            rutas["gesprog_req"] = args[i + 1]
            i += 2
        elif args[i] == "-g" and i + 1 < len(args):
            # Usamos -g en lugar de -c para evitar el error
            # tipográfico del PDF que repetía -c dos veces.
            rutas["gesprog_res"] = args[i + 1]
            i += 2
        elif args[i] == "-e" and i + 1 < len(args):
            rutas["ejecutor_req"] = args[i + 1]
            i += 2
        elif args[i] == "-d" and i + 1 < len(args):
            rutas["ejecutor_res"] = args[i + 1]
            i += 2
        else:
            i += 1

    print("[ctrllt] Iniciando...", file=sys.stderr)
    print(f"[ctrllt] Tubería cliente req : {tuberia_cliente_req}", file=sys.stderr)
    print(f"[ctrllt] Tubería cliente res : {tuberia_cliente_res}", file=sys.stderr)

    # ── PASO 3: Crear las tuberías del cliente ──
    # ctrllt crea las tuberías del cliente porque es el servidor
    # al que el cliente se conecta. El cliente no las crea.
    ipc.crear_tuberia(tuberia_cliente_req)
    ipc.crear_tuberia(tuberia_cliente_res)

    # ── PASO 4: Conectar con los servicios ──
    # ORDEN CRÍTICO: primero nos conectamos con los servicios
    # ANTES de esperar al cliente.
    # ¿Por qué? Porque los servicios ya están bloqueados esperando
    # que alguien abra su tubería para escribir.
    # Si intentáramos esperar al cliente primero, tendríamos deadlock:
    # ctrllt esperaría al cliente, los servicios esperarían a ctrllt,
    # y el cliente esperaría a ctrllt — nadie avanzaría.
    print("[ctrllt] Conectando con servicios...", file=sys.stderr)

    fds = abrir_tuberias_servicios(rutas)

    if fds is None:
        print("[ctrllt] Error al conectar con servicios. Terminando.", file=sys.stderr)
        # Limpiamos las tuberías del cliente que ya creamos.
        ipc.cerrar_tuberia(None, tuberia_cliente_req)
        ipc.cerrar_tuberia(None, tuberia_cliente_res)
        sys.exit(1)

    print("[ctrllt] Todos los servicios conectados ✓", file=sys.stderr)

    # ── PASO 5: Esperar al cliente ──
    # Ahora sí esperamos al cliente.
    # ctrllt LEE del cliente (recibe peticiones)
    # ctrllt ESCRIBE al cliente (envía respuestas)
    print("[ctrllt] Esperando conexión del cliente...", file=sys.stderr)

    fd_cliente_req = ipc.abrir_tuberia_lectura(tuberia_cliente_req)
    fd_cliente_res = ipc.abrir_tuberia_escritura(tuberia_cliente_res)

    if fd_cliente_req is None or fd_cliente_res is None:
        print("[ctrllt] Error al conectar con cliente. Terminando.", file=sys.stderr)
        cerrar_todo(fds, rutas, fd_cliente_req, fd_cliente_res,
                    tuberia_cliente_req, tuberia_cliente_res)
        sys.exit(1)

    print("[ctrllt] Cliente conectado ✓", file=sys.stderr)
    print("[ctrllt] Sistema listo. Esperando peticiones...", file=sys.stderr)

    # ── PASO 6: Loop principal ──
    while True:

        # Esperamos una petición del cliente.
        mensaje = ipc.recibir_mensaje(fd_cliente_req)

        # Si el cliente cerró su tubería, terminamos.
        if mensaje is None:
            print("[ctrllt] Cliente desconectado. Terminando.", file=sys.stderr)
            break

        operacion = mensaje.get("operacion", "")
        servicio  = mensaje.get("servicio", "")

        print(f"[ctrllt] Petición recibida — servicio: {servicio}, operacion: {operacion}", file=sys.stderr)

        # ── Operación Terminar dirigida a ctrllt ──
        # Si el cliente manda Terminar sin campo "servicio",
        # es una orden para ctrllt mismo.
        if operacion == "Terminar" and not servicio:
            print("[ctrllt] Recibida orden de terminar.", file=sys.stderr)

            # Suspendemos todos los servicios antes de terminar.
            # El profe dijo: "cuando control recibe terminar debe
            # suspender los servicios que estén corriendo".
            suspender_servicios(fds)

            # Enviamos confirmación al cliente.
            respuesta = {
                "estado": "ok",
                "datos": {"mensaje": "Sistema terminando. Servicios suspendidos."}
            }
            ipc.enviar_mensaje(fd_cliente_res, respuesta)
            break

        # ── Todas las demás peticiones se redirigen ──
        # redirigir_peticion() lee el campo "servicio",
        # envía el mensaje al servicio correcto y retorna la respuesta.
        respuesta = redirigir_peticion(mensaje, fds)

        # Enviamos la respuesta al cliente sin modificarla.
        ipc.enviar_mensaje(fd_cliente_res, respuesta)

    # ── PASO 7: Limpieza final ──
    print("[ctrllt] Cerrando sistema...", file=sys.stderr)
    cerrar_todo(fds, rutas, fd_cliente_req, fd_cliente_res,
                tuberia_cliente_req, tuberia_cliente_res)
    print("[ctrllt] Sistema terminado.", file=sys.stderr)


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    main()
