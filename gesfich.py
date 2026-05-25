# gesfich.py — Servicio de Gestión de Ficheros
#
# PROPÓSITO:
#   Este servicio administra los ficheros que serán fuente o destino
#   de los procesos de lotes. Los ficheros se guardan físicamente en
#   el directorio 'aralmac'. Se comunica con ctrllt a través de
#   dos tuberías nombradas (half-duplex en Linux).
#
# USO:
#   python3 gesfich.py -f <tuberia-peticiones> [-b <tuberia-respuestas>] -x <ruta-aralmac>
#
# EJEMPLO:
#   python3 gesfich.py -f /tmp/gesfich_req -b /tmp/gesfich_res -x ./aralmac

# ─────────────────────────────────────────────
# IMPORTACIONES
# ─────────────────────────────────────────────

import os
# Para operaciones del sistema de archivos:
# os.path.exists() → verificar si existe un archivo o directorio
# os.makedirs()    → crear directorios
# os.path.join()   → construir rutas de forma segura
# os.unlink()      → eliminar archivos

import json
# Para leer y escribir archivos .meta.json
# json.dump()  → escribe dict en archivo JSON
# json.load()  → lee archivo JSON y retorna dict

import sys
# Para leer los argumentos de línea de comandos (sys.argv)
# y para imprimir errores en sys.stderr

import shutil
# shutil.copy() copia el contenido de un archivo a otro.
# Lo usamos en la operación Actualizar para copiar
# el archivo fuente al directorio aralmac.

import ipc
# Nuestro módulo de comunicación. Contiene:
# crear_tuberia(), abrir_tuberia_lectura(), abrir_tuberia_escritura()
# enviar_mensaje(), recibir_mensaje(), cerrar_tuberia()


# ─────────────────────────────────────────────
# FUNCIÓN: leer_contador
# ─────────────────────────────────────────────

def leer_contador(aralmac):
    """
    PROPÓSITO:
        Lee el último número de identificador usado desde
        el archivo contador.txt en aralmac.
        Si el archivo no existe (primera vez), retorna 0.

    POR QUÉ EN DISCO Y NO EN MEMORIA:
        Si guardáramos el contador solo en una variable Python,
        se perdería cada vez que el servicio se reinicia.
        Al guardarlo en disco, el servicio puede continuar
        desde donde quedó aunque se haya caído.

    PARÁMETRO:
        aralmac (string): Ruta al directorio de almacenamiento.

    RETORNA:
        El último número usado (entero). Ejemplo: 3 si ya
        se crearon f-0001, f-0002 y f-0003.
    """

    # os.path.join() construye la ruta completa de forma segura.
    # En Linux une con '/': join("./aralmac", "contador.txt") → "./aralmac/contador.txt"
    # Es mejor que concatenar strings con '+' porque maneja
    # automáticamente las barras del sistema operativo.
    ruta_contador = os.path.join(aralmac, "contador_gesfich.txt")

    if not os.path.exists(ruta_contador):
        # Si no existe el contador, es la primera vez que corre el servicio.
        # Retornamos 0 para que el primer fichero sea f-0001.
        return 0

    # Abrimos el archivo en modo lectura ("r") para leer el número.
    # 'with' garantiza que el archivo se cierre automáticamente
    # al salir del bloque, incluso si hay un error.
    # Es equivalente a: f = open(...); ...; f.close()
    # pero más seguro porque close() siempre se ejecuta.
    with open(ruta_contador, "r") as f:
        # read() lee todo el contenido del archivo como string.
        # strip() elimina espacios y saltos de línea.
        # int() convierte el string a entero.
        return int(f.read().strip())


# ─────────────────────────────────────────────
# FUNCIÓN: guardar_contador
# ─────────────────────────────────────────────

def guardar_contador(aralmac, numero):
    """
    PROPÓSITO:
        Guarda el número actual del contador en disco.
        Se llama cada vez que se crea un nuevo fichero.

    PARÁMETROS:
        aralmac (string): Ruta al directorio de almacenamiento.
        numero  (int)   : El número actual a guardar.
    """

    ruta_contador = os.path.join(aralmac, "contador_gesfich.txt")

    # Abrimos en modo escritura ("w").
    # Si el archivo no existe, lo crea.
    # Si ya existe, lo sobreescribe completamente.
    with open(ruta_contador, "w") as f:
        # str(numero) convierte el entero a string para poder escribirlo.
        f.write(str(numero))


# ─────────────────────────────────────────────
# FUNCIÓN: generar_id
# ─────────────────────────────────────────────

def generar_id(aralmac):
    """
    PROPÓSITO:
        Genera un nuevo identificador único de fichero con
        formato f-XXXX (donde X es un dígito).

    CÓMO FUNCIONA:
        1. Lee el contador actual del disco.
        2. Le suma 1.
        3. Guarda el nuevo contador en disco.
        4. Retorna el identificador formateado.

    RETORNA:
        String con el nuevo identificador. Ejemplo: "f-0001"
    """

    contador = leer_contador(aralmac)
    nuevo_numero = contador + 1
    guardar_contador(aralmac, nuevo_numero)

    # f"f-{nuevo_numero:04d}" formatea el número con mínimo 4 dígitos,
    # rellenando con ceros a la izquierda.
    # Ejemplos:
    #   nuevo_numero = 1  → "f-0001"
    #   nuevo_numero = 12 → "f-0012"
    #   nuevo_numero = 999 → "f-0999"
    # El :04d significa: entero (d) con ancho mínimo 4 (04), relleno con ceros.
    return f"f-{nuevo_numero:04d}"


# ─────────────────────────────────────────────
# OPERACIÓN: op_crear
# ─────────────────────────────────────────────

def op_crear(parametros, aralmac):
    """
    PROPÓSITO:
        Crea un fichero vacío en aralmac y guarda sus metadatos.
        Retorna un dict con la respuesta JSON para ctrllt.

    PARÁMETROS:
        parametros (dict): Debe contener {"nombre": "entrada.txt"}
        aralmac    (str) : Ruta al directorio de almacenamiento.

    RETORNA:
        Dict con respuesta exitosa o de error.

    QUÉ CREA EN DISCO:
        aralmac/f-0001.txt       → el fichero vacío
        aralmac/f-0001.meta.json → metadatos (id y nombre)
    """

    # Verificamos que el parámetro 'nombre' esté presente.
    # .get() busca la clave en el dict y retorna None si no existe,
    # en vez de lanzar KeyError como haría parametros["nombre"].
    nombre = parametros.get("nombre")

    if not nombre:
        # Si nombre es None o string vacío, retornamos error.
        # Este dict será convertido a JSON por enviar_mensaje().
        return {
            "estado": "error",
            "mensaje": "El parámetro 'nombre' es obligatorio"
        }

    # Generamos un nuevo identificador único.
    id_fichero = generar_id(aralmac)

    # Construimos las rutas completas de los archivos a crear.
    # os.path.join() une la ruta base con el nombre del archivo.
    ruta_fichero = os.path.join(aralmac, f"{id_fichero}.txt")
    ruta_meta    = os.path.join(aralmac, f"{id_fichero}.meta.json")

    # Creamos el fichero vacío.
    # Abrimos en modo escritura ("w") y no escribimos nada → archivo vacío.
    # 'with' garantiza que se cierre correctamente.
    with open(ruta_fichero, "w") as f:
        pass
    # 'pass' es una instrucción que no hace nada.
    # La usamos aquí porque necesitamos el bloque 'with' para crear
    # el archivo, pero no necesitamos escribir nada dentro.

    # Creamos el archivo de metadatos con el id y el nombre descriptivo.
    # Los metadatos nos permiten saber el nombre original del fichero
    # cuando el cliente pide "Leer todos los ficheros".
    metadatos = {
        "id-fichero": id_fichero,
        "nombre": nombre
    }

    # Abrimos el archivo de metadatos en modo escritura.
    # json.dump() escribe el diccionario directamente en el archivo.
    # ensure_ascii=False permite tildes y caracteres especiales.
    # indent=2 formatea el JSON con sangría de 2 espacios (más legible).
    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(metadatos, f, ensure_ascii=False, indent=2)

    # Retornamos la respuesta exitosa.
    return {
        "estado": "ok",
        "datos": {
            "id-fichero": id_fichero,
            "nombre": nombre
        }
    }


# ─────────────────────────────────────────────
# OPERACIÓN: op_leer
# ─────────────────────────────────────────────

def op_leer(parametros, aralmac):
    """
    PROPÓSITO:
        Tiene dos formatos según el diseño de la API:
        - Formato A: recibe id-fichero → retorna contenido de ese fichero
        - Formato B: sin parámetros   → retorna lista de todos los ficheros

    CÓMO DETECTA EL FORMATO:
        Si parametros tiene la clave "id-fichero" → Formato A
        Si parametros está vacío {}               → Formato B
    """

    id_fichero = parametros.get("id-fichero")

    if id_fichero:
        # ── FORMATO A: leer un fichero específico ──

        ruta_fichero = os.path.join(aralmac, f"{id_fichero}.txt")
        ruta_meta    = os.path.join(aralmac, f"{id_fichero}.meta.json")

        # Verificamos que el fichero exista en aralmac.
        if not os.path.exists(ruta_fichero):
            return {
                "estado": "error",
                "mensaje": f"El fichero {id_fichero} no existe"
            }

        # Leemos el contenido del fichero.
        # encoding="utf-8" garantiza soporte para tildes y caracteres especiales.
        with open(ruta_fichero, "r", encoding="utf-8") as f:
            contenido = f.read()

        # Leemos los metadatos para obtener el nombre descriptivo.
        with open(ruta_meta, "r", encoding="utf-8") as f:
            metadatos = json.load(f)
        # json.load(f) lee el archivo JSON y lo convierte directamente
        # a diccionario Python. Es diferente a json.loads() que recibe
        # un string. json.load() recibe un archivo abierto.

        return {
            "estado": "ok",
            "datos": {
                "id-fichero": id_fichero,
                "nombre": metadatos["nombre"],
                "contenido": contenido
            }
        }

    else:
        # ── FORMATO B: listar todos los ficheros ──

        ficheros = []

        # os.listdir() retorna una lista con los nombres de todos
        # los archivos y carpetas en el directorio indicado.
        # Ejemplo: ["f-0001.txt", "f-0001.meta.json", "f-0002.txt", ...]
        for nombre_archivo in os.listdir(aralmac):

            # Solo nos interesan los archivos .meta.json
            # porque cada fichero registrado tiene uno.
            # endswith() verifica si el string termina con el sufijo dado.
            if nombre_archivo.endswith(".meta.json"):

                ruta_meta = os.path.join(aralmac, nombre_archivo)

                with open(ruta_meta, "r", encoding="utf-8") as f:
                    metadatos = json.load(f)

                # Agregamos solo id y nombre a la lista (no el contenido).
                ficheros.append({
                    "id-fichero": metadatos["id-fichero"],
                    "nombre":     metadatos["nombre"]
                })

        return {
            "estado": "ok",
            "datos": {
                "ficheros": ficheros
            }
        }


# ─────────────────────────────────────────────
# OPERACIÓN: op_actualizar
# ─────────────────────────────────────────────

def op_actualizar(parametros, aralmac):
    """
    PROPÓSITO:
        Copia el contenido de un archivo externo (ruta-origen)
        hacia el fichero identificado por id-fichero en aralmac.

    PARÁMETROS ESPERADOS:
        {"id-fichero": "f-0001", "ruta-origen": "/home/usuario/datos.txt"}
    """

    id_fichero  = parametros.get("id-fichero")
    ruta_origen = parametros.get("ruta-origen")

    # Verificamos que ambos parámetros estén presentes.
    if not id_fichero or not ruta_origen:
        return {
            "estado": "error",
            "mensaje": "Se requieren los parámetros 'id-fichero' y 'ruta-origen'"
        }

    ruta_fichero = os.path.join(aralmac, f"{id_fichero}.txt")

    # Verificamos que el fichero destino exista en aralmac.
    if not os.path.exists(ruta_fichero):
        return {
            "estado": "error",
            "mensaje": f"El fichero {id_fichero} no existe en aralmac"
        }

    # Verificamos que el archivo fuente exista en el disco del cliente.
    if not os.path.exists(ruta_origen):
        return {
            "estado": "error",
            "mensaje": f"El archivo fuente no existe: {ruta_origen}"
        }

    # shutil.copy(origen, destino) copia el contenido del archivo origen
    # al archivo destino. Si destino existe, lo sobreescribe.
    # shutil es "shell utilities" — utilidades de alto nivel para archivos.
    shutil.copy(ruta_origen, ruta_fichero)

    return {
        "estado": "ok",
        "datos": {
            "id-fichero": id_fichero,
            "mensaje": "Fichero actualizado correctamente"
        }
    }


# ─────────────────────────────────────────────
# OPERACIÓN: op_borrar
# ─────────────────────────────────────────────

def op_borrar(parametros, aralmac):
    """
    PROPÓSITO:
        Elimina el fichero y sus metadatos de aralmac.

    PARÁMETROS ESPERADOS:
        {"id-fichero": "f-0001"}
    """

    id_fichero = parametros.get("id-fichero")

    if not id_fichero:
        return {
            "estado": "error",
            "mensaje": "El parámetro 'id-fichero' es obligatorio"
        }

    ruta_fichero = os.path.join(aralmac, f"{id_fichero}.txt")
    ruta_meta    = os.path.join(aralmac, f"{id_fichero}.meta.json")

    if not os.path.exists(ruta_fichero):
        return {
            "estado": "error",
            "mensaje": f"El fichero {id_fichero} no existe"
        }

    # os.unlink() elimina el archivo del disco.
    # Eliminamos tanto el fichero como sus metadatos.
    os.unlink(ruta_fichero)
    os.unlink(ruta_meta)

    return {
        "estado": "ok",
        "datos": {
            "id-fichero": id_fichero,
            "mensaje": "Fichero eliminado correctamente"
        }
    }


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL: main
# ─────────────────────────────────────────────

def main():
    """
    PROPÓSITO:
        Punto de entrada del servicio gesfich.
        1. Lee los argumentos de línea de comandos.
        2. Crea y abre las tuberías.
        3. Entra al loop principal esperando peticiones.
        4. Limpia recursos al terminar.
    """

    # ── PASO 1: Leer argumentos de línea de comandos ──
    #
    # sys.argv es una lista con los argumentos que se pasaron al script.
    # Ejemplo: python3 gesfich.py -f /tmp/req -b /tmp/res -x ./aralmac
    # sys.argv → ["gesfich.py", "-f", "/tmp/req", "-b", "/tmp/res", "-x", "./aralmac"]
    #
    # Valores por defecto en caso de que no se pasen argumentos:
    tuberia_peticiones = "/tmp/gesfich_req"
    tuberia_respuestas = "/tmp/gesfich_res"
    ruta_aralmac       = "./aralmac"

    # Recorremos sys.argv buscando los flags -f, -b, -x.
    # Usamos range(1, len(sys.argv)) para saltar el primer elemento
    # que es el nombre del script ("gesfich.py").
    args = sys.argv[1:]  # Lista de argumentos sin el nombre del script.

    # Iteramos sobre los argumentos de dos en dos: flag y valor.
    # Ejemplo: ["-f", "/tmp/req", "-b", "/tmp/res", "-x", "./aralmac"]
    #           i=0   i=1         i=2   i=3          i=4   i=5
    i = 0
    while i < len(args):
        if args[i] == "-f" and i + 1 < len(args):
            # i+1 < len(args) verifica que hay un valor después del flag.
            tuberia_peticiones = args[i + 1]
            i += 2  # Avanzamos 2: saltamos el flag y su valor.
        elif args[i] == "-b" and i + 1 < len(args):
            tuberia_respuestas = args[i + 1]
            i += 2
        elif args[i] == "-x" and i + 1 < len(args):
            ruta_aralmac = args[i + 1]
            i += 2
        else:
            i += 1  # Argumento desconocido, lo saltamos.

    print(f"[gesfich] Iniciando...", file=sys.stderr)
    print(f"[gesfich] Tubería peticiones : {tuberia_peticiones}", file=sys.stderr)
    print(f"[gesfich] Tubería respuestas : {tuberia_respuestas}", file=sys.stderr)
    print(f"[gesfich] Directorio aralmac : {ruta_aralmac}", file=sys.stderr)

    # ── PASO 2: Crear el directorio aralmac si no existe ──
    #
    # os.makedirs() crea el directorio y todos los directorios
    # intermedios necesarios. exist_ok=True evita error si ya existe.
    os.makedirs(ruta_aralmac, exist_ok=True)

    # ── PASO 3: Crear las tuberías nombradas ──
    ipc.crear_tuberia(tuberia_peticiones)
    ipc.crear_tuberia(tuberia_respuestas)

    # ── PASO 4: Abrir las tuberías ──
    # IMPORTANTE: El orden importa para evitar deadlock.
    # gesfich abre primero para LEER (peticiones) y luego para ESCRIBIR (respuestas).
    # ctrllt debe hacer el orden inverso: primero ESCRIBIR, luego LEER.
    # Ambos se bloquean hasta que el otro extremo esté listo.
    print(f"[gesfich] Esperando conexión de ctrllt...", file=sys.stderr)

    fd_peticiones = ipc.abrir_tuberia_lectura(tuberia_peticiones)
    fd_respuestas = ipc.abrir_tuberia_escritura(tuberia_respuestas)

    if fd_peticiones is None or fd_respuestas is None:
        print("[gesfich] Error al abrir tuberías. Terminando.", file=sys.stderr)
        sys.exit(1)
    # sys.exit(1) termina el programa con código de error 1.
    # En Linux, exit(0) significa éxito y cualquier otro número significa error.

    print(f"[gesfich] Conectado. Esperando peticiones...", file=sys.stderr)

    # ── PASO 5: Máquina de estados ──
    # La variable 'estado' controla el comportamiento del servicio.
    # Solo puede ser "Corriendo" o "Suspendido".
    estado = "Corriendo"

    # ── PASO 6: Diccionario de operaciones CRUD ──
    # Mapea el nombre de la operación a la función que la maneja.
    # Usamos funciones lambda para pasar aralmac sin complicar la firma.
    # lambda es una función anónima de una sola expresión.
    # lambda parametros: op_crear(parametros, ruta_aralmac)
    # es equivalente a:
    # def funcion_temporal(parametros):
    #     return op_crear(parametros, ruta_aralmac)
    operaciones = {
        "Crear":      lambda p: op_crear(p, ruta_aralmac),
        "Leer":       lambda p: op_leer(p, ruta_aralmac),
        "Actualizar": lambda p: op_actualizar(p, ruta_aralmac),
        "Borrar":     lambda p: op_borrar(p, ruta_aralmac),
    }

    # ── PASO 7: Loop principal ──
    # El servicio vive aquí indefinidamente hasta recibir "Terminar".
    while True:

        # Esperamos la siguiente petición (bloquea hasta que llegue).
        mensaje = ipc.recibir_mensaje(fd_peticiones)

        # Si recibir_mensaje retorna None, la tubería se cerró.
        # Significa que ctrllt terminó inesperadamente.
        if mensaje is None:
            print("[gesfich] Tubería cerrada. Terminando.", file=sys.stderr)
            break
        # 'break' sale del while True inmediatamente.

        # Extraemos los campos del mensaje.
        # .get() con valor por defecto evita KeyError si el campo no existe.
        operacion  = mensaje.get("operacion", "")
        parametros = mensaje.get("parametros", {})

        print(f"[gesfich] Operación recibida: {operacion}", file=sys.stderr)

        # ── Manejo de operaciones de control ──
        # Estas operaciones se procesan sin importar el estado actual.

        if operacion == "Terminar":
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio terminado"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)
            break  # Salimos del loop → el servicio termina.

        elif operacion == "Suspender":
            estado = "Suspendido"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio suspendido"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        elif operacion == "Reasumir":
            estado = "Corriendo"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio reasumido"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        # ── Manejo de operaciones CRUD ──
        elif operacion in operaciones:

            if estado == "Suspendido":
                # Si está suspendido, rechazamos operaciones CRUD.
                respuesta = {
                    "estado": "error",
                    "mensaje": "Servicio suspendido. No acepta operaciones CRUD."
                }
            else:
                # Estado "Corriendo": ejecutamos la operación.
                # operaciones[operacion] obtiene la función lambda correspondiente.
                # (parametros) la llama con los parámetros del mensaje.
                funcion   = operaciones[operacion]
                respuesta = funcion(parametros)

            ipc.enviar_mensaje(fd_respuestas, respuesta)

        else:
            # Operación desconocida.
            respuesta = {
                "estado": "error",
                "mensaje": f"Operación desconocida: {operacion}"
            }
            ipc.enviar_mensaje(fd_respuestas, respuesta)

    # ── PASO 8: Limpieza al terminar ──
    # Siempre se ejecuta cuando salimos del loop (por break o Terminar).
    print("[gesfich] Cerrando y limpiando recursos...", file=sys.stderr)
    ipc.cerrar_tuberia(fd_peticiones, tuberia_peticiones)
    ipc.cerrar_tuberia(fd_respuestas, tuberia_respuestas)
    print("[gesfich] Servicio terminado.", file=sys.stderr)


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────

# Esta condición verifica si este archivo se está ejecutando
# directamente (python3 gesfich.py) y no siendo importado
# por otro módulo (import gesfich).
# Si fuera importado, main() no se ejecutaría automáticamente.
# Es una convención estándar en Python.
if __name__ == "__main__":
    main()
