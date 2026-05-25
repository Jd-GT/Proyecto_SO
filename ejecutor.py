# ejecutor.py — Servicio de Ejecución de Procesos de Lotes
#
# PROPÓSITO:
#   Este servicio lanza programas registrados en aralmac como procesos
#   de lotes, conectando sus entradas y salidas a ficheros también
#   registrados en aralmac. Puede correr múltiples lotes simultáneamente.
#
# USO:
#   python3 ejecutor.py -e <tuberia-peticiones> [-d <tuberia-respuestas>] -x <ruta-aralmac>
#
# EJEMPLO:
#   python3 ejecutor.py -e /tmp/ejecutor_req -d /tmp/ejecutor_res -x ./aralmac

# ─────────────────────────────────────────────
# IMPORTACIONES
# ─────────────────────────────────────────────

import os
# os.fork()      → duplica el proceso actual
# os.execve()    → reemplaza el proceso hijo por el programa real
# os.dup2()      → redirige file descriptors (stdin, stdout)
# os.waitpid()   → consulta el estado de un proceso hijo
# os.kill()      → envía señales a procesos (para matar)
# os.WNOHANG     → constante para waitpid no bloqueante
# os.path.join() → construye rutas de forma segura
# os.path.exists()→ verifica si existe un archivo

import sys
# sys.argv   → argumentos de línea de comandos
# sys.stderr → salida de errores

import json
# Para leer los metadatos .meta.json de los programas

import signal
# signal.SIGKILL → señal para terminar un proceso forzosamente
# signal.SIGTERM → señal para pedir a un proceso que termine

import ipc
# Nuestro módulo de comunicación por tuberías nombradas


# ─────────────────────────────────────────────
# FUNCIÓN: leer_contador
# ─────────────────────────────────────────────

def leer_contador(aralmac):
    """
    PROPÓSITO:
        Lee el último número de identificador de ejecución usado.
        Si no existe (primera vez), retorna 0.

    IDENTIFICADOR DE EJECUCIÓN:
        Formato e-XXXX. Ejemplo: e-0001, e-0002.
        La 'e' viene de 'ejecución'.
    """

    ruta_contador = os.path.join(aralmac, "contador_ejecutor.txt")

    if not os.path.exists(ruta_contador):
        return 0

    with open(ruta_contador, "r") as f:
        return int(f.read().strip())


# ─────────────────────────────────────────────
# FUNCIÓN: guardar_contador
# ─────────────────────────────────────────────

def guardar_contador(aralmac, numero):
    """
    PROPÓSITO:
        Guarda el número actual del contador en disco.
    """

    ruta_contador = os.path.join(aralmac, "contador_ejecutor.txt")

    with open(ruta_contador, "w") as f:
        f.write(str(numero))


# ─────────────────────────────────────────────
# FUNCIÓN: generar_id
# ─────────────────────────────────────────────

def generar_id(aralmac):
    """
    PROPÓSITO:
        Genera un nuevo identificador único de ejecución
        con formato e-XXXX.

    RETORNA:
        String con el nuevo identificador. Ejemplo: "e-0001"
    """

    contador = leer_contador(aralmac)
    nuevo_numero = contador + 1
    guardar_contador(aralmac, nuevo_numero)

    return f"e-{nuevo_numero:04d}"


# ─────────────────────────────────────────────
# FUNCIÓN: actualizar_estados
# ─────────────────────────────────────────────

def actualizar_estados(procesos_activos):
    """
    PROPÓSITO:
        Recorre todos los procesos activos y actualiza su estado
        consultando al sistema operativo con waitpid().

        Se llama antes de responder a cualquier petición de Estado
        para tener información actualizada.

    PARÁMETRO:
        procesos_activos (dict): El diccionario de procesos en memoria.
            Se modifica directamente (in-place).

    POR QUÉ MODIFICAR IN-PLACE:
        En Python, los diccionarios se pasan por referencia.
        Cuando modificamos procesos_activos dentro de esta función,
        los cambios se reflejan en la variable original del llamador.
        No necesitamos retornar nada.
    """

    for id_ejecucion, info in procesos_activos.items():
        # Solo consultamos procesos que aún están "corriendo".
        # No tiene sentido consultar los que ya terminaron.
        if info["estado"] == "corriendo":

            pid = info["pid"]

            try:
                # os.waitpid(pid, opciones) consulta el estado del proceso hijo.
                # Retorna una tupla (pid_retornado, codigo_estado).
                #
                # os.WNOHANG es la opción clave:
                # Sin WNOHANG → waitpid bloquea al padre hasta que el hijo termine.
                # Con WNOHANG → waitpid retorna inmediatamente sin importar si
                #               el hijo terminó o no.
                #
                # Si pid_retornado == 0: el hijo TODAVÍA está corriendo.
                # Si pid_retornado == pid: el hijo YA terminó.
                pid_retornado, codigo_estado = os.waitpid(pid, os.WNOHANG)

                if pid_retornado == pid:
                    # El proceso terminó. Actualizamos su estado.
                    # os.WIFEXITED(codigo_estado) retorna True si el proceso
                    # terminó normalmente (llamando exit() o retornando de main).
                    if os.WIFEXITED(codigo_estado):
                        # os.WEXITSTATUS() extrae el código de salida del proceso.
                        # Por convención, 0 significa éxito y cualquier otro número error.
                        codigo_salida = os.WEXITSTATUS(codigo_estado)
                        if codigo_salida == 0:
                            info["estado"] = "terminado"
                        else:
                            info["estado"] = "error"
                    else:
                        # Terminó de forma anormal (señal, kill, etc.)
                        info["estado"] = "error"

            except ChildProcessError:
                # ChildProcessError ocurre si el proceso ya no existe
                # (fue matado externamente o ya fue recogido antes).
                info["estado"] = "error"


# ─────────────────────────────────────────────
# OPERACIÓN: op_ejecutar
# ─────────────────────────────────────────────

def op_ejecutar(parametros, aralmac, procesos_activos):
    """
    PROPÓSITO:
        Lanza un programa registrado como proceso de lote.
        Usa el patrón fork-exec para no bloquear al ejecutor.

    PARÁMETROS ESPERADOS:
        {
            "id-programa": "p-0001",
            "stdin":  "f-0001",
            "stdout": "f-0002",
            "stderr": "f-0003"   ← opcional
        }

    PARÁMETROS DE LA FUNCIÓN:
        parametros      (dict): Los parámetros del mensaje JSON.
        aralmac         (str) : Ruta al directorio de almacenamiento.
        procesos_activos(dict): Diccionario de procesos en memoria.

    RETORNA:
        Dict con respuesta. Si tuvo éxito, incluye el id-ejecucion.

    FLUJO INTERNO:
        1. Validar que id-programa, stdin, stdout existen en aralmac.
        2. Leer los metadatos del programa (.meta.json).
        3. os.fork() → duplicar el proceso.
        4. HIJO: redirigir stdin/stdout con dup2(), llamar execve().
        5. PADRE: guardar el PID del hijo, retornar id-ejecucion.
    """

    # ── Extraer parámetros ──
    id_programa = parametros.get("id-programa")
    id_stdin    = parametros.get("stdin")
    id_stdout   = parametros.get("stdout")
    id_stderr   = parametros.get("stderr")  # Opcional

    # ── Validación 1: parámetros obligatorios ──
    if not id_programa or not id_stdin or not id_stdout:
        return {
            "estado": "error",
            "mensaje": "Se requieren 'id-programa', 'stdin' y 'stdout'"
        }

    # ── Validación 2: el programa existe en aralmac ──
    ruta_meta       = os.path.join(aralmac, f"{id_programa}.meta.json")
    ruta_ejecutable = os.path.join(aralmac, f"{id_programa}.ejecutable")

    if not os.path.exists(ruta_meta):
        return {
            "estado": "error",
            "mensaje": f"El programa {id_programa} no existe en aralmac"
        }

    # ── Validación 3: el fichero stdin existe en aralmac ──
    ruta_stdin = os.path.join(aralmac, f"{id_stdin}.txt")

    if not os.path.exists(ruta_stdin):
        return {
            "estado": "error",
            "mensaje": f"El fichero stdin {id_stdin} no existe en aralmac"
        }

    # ── Validación 4: el fichero stdout existe en aralmac ──
    ruta_stdout = os.path.join(aralmac, f"{id_stdout}.txt")

    if not os.path.exists(ruta_stdout):
        return {
            "estado": "error",
            "mensaje": f"El fichero stdout {id_stdout} no existe en aralmac"
        }

    # ── Leer metadatos del programa ──
    # Necesitamos los args y env para pasárselos a execve().
    with open(ruta_meta, "r", encoding="utf-8") as f:
        metadatos = json.load(f)

    # El ejecutable almacenado en aralmac es la copia física.
    # Usamos la ruta dentro de aralmac, no la original.
    ejecutable = ruta_ejecutable
    args       = metadatos.get("args", [])
    env_lista  = metadatos.get("env", [])

    # execve() necesita el ambiente como diccionario {clave: valor}.
    # Pero lo guardamos como lista ["CLAVE=valor", "CLAVE2=valor2"].
    # Necesitamos convertirlo.
    # Ejemplo: ["PATH=/usr/bin", "LANG=es"] → {"PATH": "/usr/bin", "LANG": "es"}
    env_dict = {}
    for variable in env_lista:
        # split("=", 1) divide el string en máximo 2 partes por el "=".
        # El 1 es importante: si el valor tiene "=" (ejemplo: "URL=http://a=b"),
        # solo divide por el primer "=" y deja el resto intacto.
        if "=" in variable:
            clave, valor = variable.split("=", 1)
            env_dict[clave] = valor

    # Si env está vacío, usamos el ambiente actual del sistema.
    # os.environ es un diccionario con todas las variables de ambiente
    # del proceso actual. Es como hacer 'env' en la terminal.
    if not env_dict:
        env_dict = dict(os.environ)

    # ── Abrir ficheros de entrada y salida ANTES del fork ──
    # Los abrimos aquí (en el padre) para poder verificar errores
    # antes de hacer fork. Si los abriéramos en el hijo y fallaran,
    # no podríamos retornar un error limpio a ctrllt.
    try:
        fd_stdin  = open(ruta_stdin,  "r")
        fd_stdout = open(ruta_stdout, "w")

        # stderr es opcional. Si no viene, usamos /dev/null.
        # /dev/null es un archivo especial de Linux que descarta
        # todo lo que se escribe en él. Es el "agujero negro" del sistema.
        if id_stderr:
            ruta_stderr = os.path.join(aralmac, f"{id_stderr}.txt")
            if os.path.exists(ruta_stderr):
                fd_stderr = open(ruta_stderr, "w")
            else:
                fd_stderr = open("/dev/null", "w")
        else:
            fd_stderr = open("/dev/null", "w")

    except OSError as e:
        return {
            "estado": "error",
            "mensaje": f"Error al abrir ficheros: {e}"
        }

    # ── El patrón fork-exec ──
    #
    # os.fork() duplica el proceso actual.
    # A partir de aquí, DOS procesos ejecutan el código simultáneamente.
    # La única diferencia es el valor que retorna fork():
    #   En el PADRE: retorna el PID del hijo (número > 0)
    #   En el HIJO:  retorna 0
    pid = os.fork()

    if pid == 0:
        # ═══════════════════════════════════════
        # CÓDIGO DEL HIJO
        # Este bloque solo lo ejecuta el proceso hijo.
        # El objetivo es convertirse en el programa del lote.
        # ═══════════════════════════════════════

        try:
            # ── Redirigir stdin (0) al fichero de entrada ──
            # os.dup2(fd_origen, fd_destino) hace que fd_destino
            # apunte al mismo archivo que fd_origen.
            # fd_stdin.fileno() obtiene el número entero del file descriptor.
            # Después de esto, cuando el programa lea de stdin (fd 0),
            # en realidad leerá del fichero f-0001.txt.
            os.dup2(fd_stdin.fileno(), 0)

            # ── Redirigir stdout (1) al fichero de salida ──
            # Después de esto, cuando el programa imprima a stdout (fd 1),
            # en realidad escribirá en f-0002.txt.
            os.dup2(fd_stdout.fileno(), 1)

            # ── Redirigir stderr (2) ──
            # Después de esto, los errores del programa van a f-0003.txt
            # o a /dev/null si no se especificó stderr.
            os.dup2(fd_stderr.fileno(), 2)

            # ── Cerrar los file descriptors originales ──
            # Después de dup2(), ya no necesitamos los originales.
            # Si no los cerramos, el proceso tendría descriptores
            # duplicados abiertos innecesariamente.
            fd_stdin.close()
            fd_stdout.close()
            fd_stderr.close()

            # ── Construir argv para execve ──
            # execve necesita una lista donde el primer elemento
            # es el nombre del programa y el resto son los argumentos.
            # Ejemplo: ["/usr/bin/python3", "script.py", "--verbose"]
            #
            # IMPORTANTE: argv[0] debe ser el nombre ORIGINAL del ejecutable,
            # NO la ruta dentro de aralmac (p-0001.ejecutable).
            # Algunos programas como /bin/cat usan argv[0] para saber
            # qué función ejecutar. Si argv[0] es "p-0001.ejecutable",
            # cat no lo reconoce y falla con "unknown program".
            # Por eso usamos metadatos["ejecutable"] (la ruta original)
            # como argv[0], pero ejecutamos la copia física en aralmac.
            argv = [metadatos["ejecutable"]] + args

            # ── os.execve() — el momento de la transformación ──
            # Este es el punto donde el hijo deja de ser una copia
            # del ejecutor y se convierte en el programa del lote.
            #
            # os.execve(ruta, argv, env) recibe:
            #   ruta: la ruta al ejecutable
            #   argv: lista de argumentos (primer elemento = nombre del programa)
            #   env:  diccionario de variables de ambiente
            #
            # IMPORTANTE: si execve tiene éxito, NUNCA retorna.
            # El proceso hijo se convirtió en otro programa.
            # Si execve falla (programa no existe, sin permisos),
            # lanza una excepción OSError.
            os.execve(ejecutable, argv, env_dict)

        except OSError as e:
            # Si execve falla, imprimimos el error y salimos del hijo.
            # os._exit() termina el proceso hijo inmediatamente.
            # Usamos os._exit() y NO sys.exit() porque sys.exit()
            # ejecuta código de limpieza de Python (atexit, destructores)
            # que podría interferir con el proceso padre.
            # os._exit(1) termina sin limpieza — directo al sistema operativo.
            print(f"[hijo] Error en execve: {e}", file=sys.stderr)
            os._exit(1)

    else:
        # ═══════════════════════════════════════
        # CÓDIGO DEL PADRE
        # pid contiene el PID del hijo (número > 0).
        # El padre sigue siendo el ejecutor.
        # ═══════════════════════════════════════

        # Cerramos los file descriptors en el padre también.
        # El padre no los necesita — son del hijo.
        # Si no los cerramos, cuando el hijo termine y cierre
        # su extremo, el archivo no se liberaría completamente
        # porque el padre todavía lo tendría abierto.
        fd_stdin.close()
        fd_stdout.close()
        fd_stderr.close()

        # Generamos el identificador de esta ejecución.
        id_ejecucion = generar_id(aralmac)

        # Guardamos la información del proceso en el diccionario en memoria.
        # Este diccionario persiste mientras el ejecutor esté corriendo.
        procesos_activos[id_ejecucion] = {
            "pid":         pid,          # PID del proceso hijo en Linux
            "estado":      "corriendo",  # Estado inicial
            "id-programa": id_programa,
            "stdin":       id_stdin,
            "stdout":      id_stdout,
            "stderr":      id_stderr
        }

        print(f"[ejecutor] Lote {id_ejecucion} iniciado con PID {pid}", file=sys.stderr)

        return {
            "estado": "ok",
            "datos": {
                "id-ejecucion": id_ejecucion,
                "mensaje": "Lote iniciado correctamente"
            }
        }


# ─────────────────────────────────────────────
# OPERACIÓN: op_estado
# ─────────────────────────────────────────────

def op_estado(parametros, procesos_activos):
    """
    PROPÓSITO:
        Consulta el estado de uno o todos los lotes en ejecución.

    FORMATO A — Estado de un lote específico:
        {"id-ejecucion": "e-0001"}

    FORMATO B — Estado de todos los lotes (sin parámetros):
        {}
    """

    # Actualizamos los estados antes de responder.
    # Así el cliente recibe información fresca del sistema operativo.
    actualizar_estados(procesos_activos)

    id_ejecucion = parametros.get("id-ejecucion")

    if id_ejecucion:
        # ── Formato A: un lote específico ──

        if id_ejecucion not in procesos_activos:
            return {
                "estado": "error",
                "mensaje": f"La ejecución {id_ejecucion} no existe"
            }

        info = procesos_activos[id_ejecucion]

        return {
            "estado": "ok",
            "datos": {
                "id-ejecucion": id_ejecucion,
                "estado-ejecucion": info["estado"]
            }
        }

    else:
        # ── Formato B: todos los lotes ──

        lista = []
        for id_ejec, info in procesos_activos.items():
            lista.append({
                "id-ejecucion":    id_ejec,
                "estado-ejecucion": info["estado"]
            })

        return {
            "estado": "ok",
            "datos": {
                "ejecuciones": lista
            }
        }


# ─────────────────────────────────────────────
# OPERACIÓN: op_matar
# ─────────────────────────────────────────────

def op_matar(parametros, procesos_activos):
    """
    PROPÓSITO:
        Termina forzosamente un proceso de lote en ejecución.
        Envía la señal SIGKILL al proceso hijo.

    PARÁMETROS ESPERADOS:
        {"id-ejecucion": "e-0001"}

    QUÉ ES UNA SEÑAL:
        En Linux, las señales son mensajes que el sistema operativo
        puede enviar a los procesos. Son interrupciones asíncronas.
        SIGKILL (señal 9) termina el proceso inmediatamente
        sin darle oportunidad de hacer limpieza.
        SIGTERM (señal 15) pide al proceso que termine gentilmente.
        Usamos SIGKILL porque el cliente quiere terminar forzosamente.
    """

    id_ejecucion = parametros.get("id-ejecucion")

    if not id_ejecucion:
        return {
            "estado": "error",
            "mensaje": "El parámetro 'id-ejecucion' es obligatorio"
        }

    if id_ejecucion not in procesos_activos:
        return {
            "estado": "error",
            "mensaje": f"La ejecución {id_ejecucion} no existe"
        }

    info = procesos_activos[id_ejecucion]

    if info["estado"] != "corriendo":
        return {
            "estado": "error",
            "mensaje": f"La ejecución {id_ejecucion} no está corriendo"
        }

    pid = info["pid"]

    try:
        # os.kill(pid, señal) envía una señal al proceso con ese PID.
        # signal.SIGKILL es la señal 9 — termina el proceso inmediatamente.
        # El proceso no puede ignorar ni capturar SIGKILL.
        os.kill(pid, signal.SIGKILL)

        # Recogemos el proceso terminado para evitar que quede
        # como "proceso zombie" en el sistema.
        # Un zombie es un proceso que terminó pero cuyo estado
        # no fue recogido por el padre con waitpid().
        # Los zombies ocupan entradas en la tabla de procesos del kernel.
        # waitpid() con 0 (bloqueante) es seguro aquí porque acabamos
        # de matar al hijo — terminará casi instantáneamente.
        os.waitpid(pid, 0)

        # Actualizamos el estado en nuestro diccionario.
        info["estado"] = "terminado"

        return {
            "estado": "ok",
            "datos": {
                "id-ejecucion": id_ejecucion,
                "mensaje": "Ejecución terminada forzosamente"
            }
        }

    except ProcessLookupError:
        # ProcessLookupError ocurre si el proceso ya no existe
        # cuando intentamos matarlo (terminó justo antes de kill).
        info["estado"] = "terminado"
        return {
            "estado": "ok",
            "datos": {
                "id-ejecucion": id_ejecucion,
                "mensaje": "El proceso ya había terminado"
            }
        }

    except PermissionError:
        # PermissionError ocurre si no tenemos permisos para
        # enviar señales a ese proceso.
        return {
            "estado": "error",
            "mensaje": f"Sin permisos para terminar la ejecución {id_ejecucion}"
        }


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL: main
# ─────────────────────────────────────────────

def main():
    """
    PROPÓSITO:
        Punto de entrada del servicio ejecutor.
        Igual en estructura a gesfich y gesprog, pero con
        el diccionario procesos_activos en memoria.
    """

    # ── PASO 1: Valores por defecto ──
    tuberia_peticiones = "/tmp/ejecutor_req"
    tuberia_respuestas = "/tmp/ejecutor_res"
    ruta_aralmac       = "./aralmac"

    # ── PASO 2: Leer argumentos de línea de comandos ──
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] == "-e" and i + 1 < len(args):
            tuberia_peticiones = args[i + 1]
            i += 2
        elif args[i] == "-d" and i + 1 < len(args):
            tuberia_respuestas = args[i + 1]
            i += 2
        elif args[i] == "-x" and i + 1 < len(args):
            ruta_aralmac = args[i + 1]
            i += 2
        else:
            i += 1

    print(f"[ejecutor] Iniciando...", file=sys.stderr)
    print(f"[ejecutor] Tubería peticiones : {tuberia_peticiones}", file=sys.stderr)
    print(f"[ejecutor] Tubería respuestas : {tuberia_respuestas}", file=sys.stderr)
    print(f"[ejecutor] Directorio aralmac : {ruta_aralmac}", file=sys.stderr)

    # ── PASO 3: Crear directorio aralmac si no existe ──
    os.makedirs(ruta_aralmac, exist_ok=True)

    # ── PASO 4: Crear tuberías ──
    ipc.crear_tuberia(tuberia_peticiones)
    ipc.crear_tuberia(tuberia_respuestas)

    # ── PASO 5: Abrir tuberías ──
    print(f"[ejecutor] Esperando conexión de ctrllt...", file=sys.stderr)

    fd_peticiones = ipc.abrir_tuberia_lectura(tuberia_peticiones)
    fd_respuestas = ipc.abrir_tuberia_escritura(tuberia_respuestas)

    if fd_peticiones is None or fd_respuestas is None:
        print("[ejecutor] Error al abrir tuberías. Terminando.", file=sys.stderr)
        sys.exit(1)

    print(f"[ejecutor] Conectado. Esperando peticiones...", file=sys.stderr)

    # ── PASO 6: Diccionario de procesos activos en memoria ──
    # Este diccionario vive mientras el ejecutor esté corriendo.
    # Se pierde si el ejecutor reinicia — es comportamiento esperado
    # porque los PIDs tampoco sobreviven un reinicio.
    procesos_activos = {}

    # ── PASO 7: Máquina de estados ──
    estado = "Corriendo"

    # ── PASO 8: Loop principal ──
    while True:

        mensaje = ipc.recibir_mensaje(fd_peticiones)

        if mensaje is None:
            print("[ejecutor] Tubería cerrada. Terminando.", file=sys.stderr)
            break

        operacion  = mensaje.get("operacion", "")
        parametros = mensaje.get("parametros", {})

        print(f"[ejecutor] Operación recibida: {operacion}", file=sys.stderr)

        # ── Operaciones de control ──

        if operacion == "Terminar":
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio terminado"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)
            break

        elif operacion == "Suspender":
            # IMPORTANTE: al suspender, los lotes que ya están corriendo
            # CONTINÚAN ejecutándose. Solo dejamos de aceptar nuevas
            # peticiones de Ejecutar.
            # Los procesos hijos son independientes — viven en el kernel
            # de Linux y el ejecutor no necesita hacer nada para
            # que sigan corriendo.
            estado = "Suspendido"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio suspendido. Los lotes activos continúan."}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        elif operacion == "Reasumir":
            estado = "Corriendo"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio reasumido"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        elif operacion == "Parar":
            # Parar: el ejecutor deja de aceptar nuevas ejecuciones
            # pero espera a que los lotes activos terminen.
            # Por ahora lo tratamos como Suspender.
            estado = "Parado"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio en estado parado"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        # ── Estado: se permite en cualquier estado del servicio ──
        elif operacion == "Estado":
            respuesta = op_estado(parametros, procesos_activos)
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        # ── Matar: se permite en cualquier estado del servicio ──
        elif operacion == "Matar":
            respuesta = op_matar(parametros, procesos_activos)
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        # ── Ejecutar: solo en estado Corriendo ──
        elif operacion == "Ejecutar":
            if estado != "Corriendo":
                respuesta = {
                    "estado": "error",
                    "mensaje": f"Servicio en estado {estado}. No acepta nuevas ejecuciones."
                }
            else:
                respuesta = op_ejecutar(parametros, ruta_aralmac, procesos_activos)

            ipc.enviar_mensaje(fd_respuestas, respuesta)

        else:
            respuesta = {
                "estado": "error",
                "mensaje": f"Operación desconocida: {operacion}"
            }
            ipc.enviar_mensaje(fd_respuestas, respuesta)

    # ── PASO 9: Limpieza al terminar ──
    print("[ejecutor] Cerrando y limpiando recursos...", file=sys.stderr)
    ipc.cerrar_tuberia(fd_peticiones, tuberia_peticiones)
    ipc.cerrar_tuberia(fd_respuestas, tuberia_respuestas)
    print("[ejecutor] Servicio terminado.", file=sys.stderr)


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    main()
