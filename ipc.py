# ipc.py — Módulo de Comunicación Entre Procesos (IPC)
#
# PROPÓSITO DE ESTE ARCHIVO:
# Este módulo centraliza toda la lógica de las tuberías nombradas (named pipes).
# Todos los servicios (gesfich, gesprog, ejecutor, ctrllt) lo importan y usan
# sus funciones. Así si hay un bug en la comunicación, se corrige en un solo lugar.
#
# PRINCIPIO: DRY — Don't Repeat Yourself (No te repitas).

# ─────────────────────────────────────────────
# IMPORTACIONES
# ─────────────────────────────────────────────

import os
# 'os' es el módulo que nos permite hablar con el sistema operativo Linux.
# A través de él usamos: os.mkfifo() para crear tuberías,
# os.path.exists() para verificar si un archivo existe,
# y os.unlink() para eliminar archivos.

import json
# 'json' es el módulo para convertir entre diccionarios Python y texto JSON.
# json.dumps(dict) → convierte un diccionario a texto JSON (string)
# json.loads(texto) → convierte texto JSON a diccionario Python

import sys
# 'sys' nos permite interactuar con el intérprete de Python.
# Lo usamos principalmente para sys.stderr.write() que imprime
# mensajes de error en la salida de error estándar (no en la salida normal).


# ─────────────────────────────────────────────
# FUNCIÓN 1: crear_tuberia
# ─────────────────────────────────────────────

def crear_tuberia(ruta):
    """
    PROPÓSITO:
        Crea un archivo FIFO (tubería nombrada) en el disco si no existe.

    PARÁMETRO:
        ruta (string): La ruta completa donde se creará el archivo FIFO.
                       Ejemplo: "/tmp/tuberia_gesfich_req"

    RETORNA:
        True  → si la tubería fue creada o ya existía (todo bien)
        False → si hubo un error inesperado

    POR QUÉ VERIFICAMOS SI YA EXISTE:
        os.mkfifo() lanza FileExistsError si el archivo ya existe.
        Esto pasaría si el servicio se cayó sin limpiar sus tuberías.
        En vez de que el programa explote, verificamos primero.
    """

    try:
        # os.path.exists(ruta) le pregunta al sistema operativo:
        # "¿existe un archivo (de cualquier tipo) en esta ruta?"
        # Devuelve True o False.
        if not os.path.exists(ruta):

            # os.mkfifo(ruta) le pide a Linux que cree un archivo especial
            # de tipo FIFO en la ruta indicada.
            # Este archivo NO almacena datos — es solo un canal de comunicación.
            # En disco se ve con 'ls -la' como: prw-r--r-- ... tuberia_req
            # La 'p' al inicio significa 'pipe' (tubería).
            os.mkfifo(ruta)

            # Imprimimos en stderr (salida de error estándar) para informar
            # que la tubería fue creada. Usamos stderr y no print() para
            # separar mensajes del sistema de la salida normal del programa.
            print(f"[ipc] Tubería creada: {ruta}", file=sys.stderr)

        else:
            # Si ya existía, simplemente lo informamos. No es un error.
            print(f"[ipc] Tubería ya existe, reutilizando: {ruta}", file=sys.stderr)

        return True

    except OSError as e:
        # OSError es la excepción que lanza Python cuando una operación
        # del sistema operativo falla. Por ejemplo, si no tienes permisos
        # para crear archivos en esa ruta.
        # 'e' contiene el detalle del error (número y mensaje).
        print(f"[ipc] Error al crear tubería {ruta}: {e}", file=sys.stderr)
        return False


# ─────────────────────────────────────────────
# FUNCIÓN 2: abrir_tuberia_lectura
# ─────────────────────────────────────────────

def abrir_tuberia_lectura(ruta):
    """
    PROPÓSITO:
        Abre una tubería nombrada en modo lectura.
        Esta función BLOQUEA al proceso que la llama hasta que
        otro proceso abra la misma tubería en modo escritura.

    PARÁMETRO:
        ruta (string): La ruta del archivo FIFO a abrir.

    RETORNA:
        El file descriptor (objeto de archivo abierto) si tuvo éxito.
        None si hubo un error.

    QUÉ ES UN FILE DESCRIPTOR:
        Es el "control remoto" de la tubería. Una vez abierta,
        usas este objeto para leer datos con fd.readline().
        La variable se llama convencionalmente 'fd' de 'file descriptor'.

    POR QUÉ BLOQUEA:
        Linux exige que ambos extremos de la tubería estén abiertos
        antes de permitir comunicación. Si abres para leer y nadie
        ha abierto para escribir, Linux te dice "espera".
        Esto es correcto y esperado — el servicio espera al controlador.
    """

    try:
        # open(ruta, "r") abre el archivo en modo lectura.
        # Para una tubería FIFO, esta línea bloquea hasta que
        # otro proceso haga open(ruta, "w") en la misma ruta.
        # El modo "r" significa Read (solo lectura).
        fd = open(ruta, "r")

        print(f"[ipc] Tubería abierta para lectura: {ruta}", file=sys.stderr)

        # Retornamos el file descriptor para que el llamador pueda usarlo
        # en recibir_mensaje(fd).
        return fd

    except OSError as e:
        print(f"[ipc] Error al abrir tubería para lectura {ruta}: {e}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────
# FUNCIÓN 3: abrir_tuberia_escritura
# ─────────────────────────────────────────────

def abrir_tuberia_escritura(ruta):
    """
    PROPÓSITO:
        Abre una tubería nombrada en modo escritura.
        Esta función también BLOQUEA hasta que otro proceso
        abra la misma tubería en modo lectura.

    PARÁMETRO:
        ruta (string): La ruta del archivo FIFO a abrir.

    RETORNA:
        El file descriptor si tuvo éxito.
        None si hubo un error.

    NOTA IMPORTANTE:
        El orden de apertura importa para evitar deadlocks.
        En este proyecto: primero abre el LECTOR (el servicio),
        luego abre el ESCRITOR (ctrllt).
        Por eso los servicios deben arrancar ANTES que ctrllt.
    """

    try:
        # open(ruta, "w") abre en modo escritura.
        # El modo "w" significa Write (solo escritura).
        # También bloquea hasta que el lector esté listo.
        fd = open(ruta, "w")

        print(f"[ipc] Tubería abierta para escritura: {ruta}", file=sys.stderr)

        return fd

    except OSError as e:
        print(f"[ipc] Error al abrir tubería para escritura {ruta}: {e}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────
# FUNCIÓN 4: enviar_mensaje
# ─────────────────────────────────────────────

def enviar_mensaje(fd, datos):
    """
    PROPÓSITO:
        Convierte un diccionario Python a texto JSON y lo envía
        por la tubería. Agrega un salto de línea al final para
        que el receptor sepa dónde termina el mensaje.

    PARÁMETROS:
        fd    : El file descriptor de una tubería abierta para escritura.
                Debe haber sido obtenido con abrir_tuberia_escritura().
        datos : Un diccionario Python con el mensaje a enviar.
                Ejemplo: {"estado": "ok", "id-fichero": "f-0001"}

    RETORNA:
        True  → si el mensaje fue enviado correctamente.
        False → si hubo un error.

    POR QUÉ \n AL FINAL:
        La función recibir_mensaje usa readline() que lee hasta
        encontrar un salto de línea '\n'. Sin el '\n', el receptor
        esperaría indefinidamente porque nunca encontraría el fin
        del mensaje. Es el "punto final" del mensaje.

    POR QUÉ flush():
        Python no envía los datos inmediatamente cuando llamas write().
        Los guarda en un buffer (memoria temporal) por eficiencia.
        flush() fuerza el envío inmediato. Sin flush(), el receptor
        podría esperar para siempre aunque write() ya se ejecutó.
    """

    try:
        # json.dumps(datos) convierte el diccionario a texto JSON.
        # Ejemplo:
        #   datos = {"estado": "ok", "id-fichero": "f-0001"}
        #   json.dumps(datos) → '{"estado": "ok", "id-fichero": "f-0001"}'
        # ensure_ascii=False permite caracteres especiales como tildes (á, é, etc.)
        texto = json.dumps(datos, ensure_ascii=False)

        # Escribimos el texto JSON seguido de '\n' (salto de línea).
        # El '\n' es el delimitador — le dice al receptor "aquí termina el mensaje".
        fd.write(texto + "\n")

        # Forzamos el envío inmediato vaciando el buffer de Python.
        # Sin esto, el mensaje podría quedar atrapado en memoria
        # y el receptor nunca lo recibiría.
        fd.flush()

        return True

    except OSError as e:
        # OSError aquí puede significar que la tubería se cerró
        # inesperadamente (el proceso del otro lado terminó).
        print(f"[ipc] Error al enviar mensaje: {e}", file=sys.stderr)
        return False

    except (TypeError, ValueError) as e:
        # TypeError  → si 'datos' contiene algo que json.dumps no puede convertir
        # ValueError → si el diccionario tiene estructura inválida para JSON
        print(f"[ipc] Error al serializar mensaje a JSON: {e}", file=sys.stderr)
        return False


# ─────────────────────────────────────────────
# FUNCIÓN 5: recibir_mensaje
# ─────────────────────────────────────────────

def recibir_mensaje(fd):
    """
    PROPÓSITO:
        Lee una línea de texto de la tubería y la convierte
        de JSON a diccionario Python.

    PARÁMETRO:
        fd : El file descriptor de una tubería abierta para lectura.
             Debe haber sido obtenido con abrir_tuberia_lectura().

    RETORNA:
        Un diccionario Python con el mensaje recibido.
        None → si la tubería se cerró (el otro proceso terminó)
               o si hubo un error de formato JSON.

    POR QUÉ readline():
        readline() lee caracteres hasta encontrar '\n' y retorna
        todo lo leído incluyendo el '\n'.
        Si no hay datos disponibles, BLOQUEA esperando.
        Esto es correcto: el servicio espera pacientemente
        la siguiente petición sin consumir CPU.

    POR QUÉ strip():
        readline() incluye el '\n' al final del texto.
        strip() elimina espacios en blanco y saltos de línea
        de los extremos del texto.
        Ejemplo: '{"operacion": "Crear"}\n' → '{"operacion": "Crear"}'
        Si no hiciéramos strip(), json.loads() podría fallar
        con algunos intérpretes.
    """

    try:
        # readline() bloquea hasta que llegue una línea completa (terminada en '\n').
        # Retorna el texto incluyendo el '\n' al final.
        # Si la tubería se cerró (el escritor hizo close()), retorna '' (string vacío).
        linea = fd.readline()

        # Si readline() retornó string vacío, significa que el escritor
        # cerró la tubería. No es un error — es una señal de desconexión.
        if linea == "":
            print("[ipc] Tubería cerrada por el escritor.", file=sys.stderr)
            return None

        # strip() elimina el '\n' del final y cualquier espacio extra.
        # Necesitamos el texto limpio para que json.loads() funcione.
        texto_limpio = linea.strip()

        # json.loads(texto) convierte el texto JSON a diccionario Python.
        # Ejemplo:
        #   texto = '{"operacion": "Crear", "parametros": {"nombre": "f.txt"}}'
        #   json.loads(texto) → {"operacion": "Crear", "parametros": {"nombre": "f.txt"}}
        datos = json.loads(texto_limpio)

        return datos

    except json.JSONDecodeError as e:
        # JSONDecodeError ocurre si el texto recibido no es JSON válido.
        # Ejemplo: si se recibió texto corrupto o incompleto.
        print(f"[ipc] Error: mensaje recibido no es JSON válido: {e}", file=sys.stderr)
        print(f"[ipc] Texto recibido: '{linea}'", file=sys.stderr)
        return None

    except OSError as e:
        print(f"[ipc] Error al leer de la tubería: {e}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────
# FUNCIÓN 6: cerrar_tuberia
# ─────────────────────────────────────────────

def cerrar_tuberia(fd, ruta):
    """
    PROPÓSITO:
        Cierra la conexión con la tubería y elimina el archivo
        FIFO del disco. Se llama cuando el servicio va a terminar.

    PARÁMETROS:
        fd   : El file descriptor a cerrar. Puede ser None si
               la tubería nunca se abrió correctamente.
        ruta : La ruta del archivo FIFO a eliminar del disco.

    POR QUÉ ELIMINAR EL ARCHIVO:
        Si no eliminamos el FIFO, la próxima vez que el servicio
        arranque, os.mkfifo() fallará con FileExistsError.
        Es una limpieza obligatoria.

    POR QUÉ VERIFICAMOS fd IS NOT None:
        Si abrir_tuberia_lectura() o abrir_tuberia_escritura()
        fallaron, retornaron None. Llamar None.close() lanzaría
        AttributeError. Verificamos primero para evitar ese crash.
    """

    # Solo cerramos el file descriptor si existe (no es None).
    if fd is not None:
        try:
            # close() le dice al sistema operativo que ya no usaremos
            # este file descriptor. Libera recursos internos del OS.
            fd.close()
            print(f"[ipc] File descriptor cerrado.", file=sys.stderr)
        except OSError as e:
            print(f"[ipc] Error al cerrar file descriptor: {e}", file=sys.stderr)

    # Eliminamos el archivo FIFO del disco si existe.
    if os.path.exists(ruta):
        try:
            # os.unlink(ruta) elimina el archivo del sistema de archivos.
            # Es equivalente a ejecutar 'rm ruta' en la terminal.
            os.unlink(ruta)
            print(f"[ipc] Tubería eliminada del disco: {ruta}", file=sys.stderr)
        except OSError as e:
            print(f"[ipc] Error al eliminar tubería {ruta}: {e}", file=sys.stderr)
