# gesprog.py — Servicio de Gestión de Programas
#
# PROPÓSITO:
#   Este servicio administra los programas (ejecutables) que serán
#   utilizados por el ejecutor. Guarda una copia del ejecutable y sus
#   metadatos (argumentos y variables de ambiente) en el directorio aralmac.
#   Se comunica con ctrllt a través de dos tuberías nombradas.
#
# USO:
#   python3 gesprog.py -p <tuberia-peticiones> [-c <tuberia-respuestas>] -x <ruta-aralmac>
#
# EJEMPLO:
#   python3 gesprog.py -p /tmp/gesprog_req -c /tmp/gesprog_res -x ./aralmac

# ─────────────────────────────────────────────
# IMPORTACIONES
# ─────────────────────────────────────────────

import os
# os.path.exists()  → verificar si existe un archivo
# os.access()       → verificar permisos de ejecución
# os.makedirs()     → crear directorios
# os.path.join()    → construir rutas de forma segura
# os.unlink()       → eliminar archivos

import json
# json.dump()  → escribe dict en archivo JSON
# json.load()  → lee archivo JSON y retorna dict

import sys
# sys.argv    → argumentos de línea de comandos
# sys.stderr  → salida de errores

import shutil
# shutil.copy() → copia archivos de una ruta a otra

import ipc
# Nuestro módulo de comunicación por tuberías nombradas


# ─────────────────────────────────────────────
# FUNCIÓN: leer_contador
# ─────────────────────────────────────────────

def leer_contador(aralmac):
    """
    PROPÓSITO:
        Lee el último número de identificador usado desde
        el archivo contador_gesprog.txt en aralmac.
        Si no existe (primera vez), retorna 0.

    NOTA:
        Usamos contador_gesprog.txt (no contador_gesfich.txt)
        para no confundir los contadores de ambos servicios.
        Cada servicio tiene su propio contador independiente.
    """

    ruta_contador = os.path.join(aralmac, "contador_gesprog.txt")

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
        Se llama cada vez que se registra un nuevo programa.
    """

    ruta_contador = os.path.join(aralmac, "contador_gesprog.txt")

    with open(ruta_contador, "w") as f:
        f.write(str(numero))


# ─────────────────────────────────────────────
# FUNCIÓN: generar_id
# ─────────────────────────────────────────────

def generar_id(aralmac):
    """
    PROPÓSITO:
        Genera un nuevo identificador único de programa
        con formato p-XXXX (donde X es un dígito).

    RETORNA:
        String con el nuevo identificador. Ejemplo: "p-0001"

    CÓMO FUNCIONA:
        1. Lee el contador actual del disco.
        2. Le suma 1.
        3. Guarda el nuevo contador en disco.
        4. Retorna el identificador formateado.
    """

    contador = leer_contador(aralmac)
    nuevo_numero = contador + 1
    guardar_contador(aralmac, nuevo_numero)

    # f"p-{nuevo_numero:04d}" formatea el número con mínimo
    # 4 dígitos rellenando con ceros a la izquierda.
    # Ejemplos:
    #   1  → "p-0001"
    #   12 → "p-0012"
    return f"p-{nuevo_numero:04d}"


# ─────────────────────────────────────────────
# OPERACIÓN: op_guardar
# ─────────────────────────────────────────────

def op_guardar(parametros, aralmac):
    """
    PROPÓSITO:
        Registra un ejecutable en aralmac con sus argumentos
        y variables de ambiente. Retorna el id-programa generado.

    PARÁMETROS ESPERADOS:
        {
            "ejecutable": "/usr/bin/python3",
            "args": ["script.py", "--verbose"],
            "env": ["LANG=es_CO.UTF-8", "PATH=/usr/bin"]
        }

    QUÉ CREA EN DISCO:
        aralmac/p-0001.ejecutable   → copia física del ejecutable
        aralmac/p-0001.meta.json    → metadatos del programa

    VALIDACIONES:
        1. El parámetro 'ejecutable' debe estar presente.
        2. El archivo ejecutable debe existir en disco.
        3. El archivo debe tener permisos de ejecución.
    """

    # Extraemos los parámetros del mensaje.
    # .get() con valor por defecto evita KeyError.
    ejecutable = parametros.get("ejecutable")
    args       = parametros.get("args", [])
    env        = parametros.get("env", [])
    # Si no se pasan args o env, usamos listas vacías por defecto.
    # [] es una lista vacía en Python.

    # Validación 1: el campo ejecutable es obligatorio.
    if not ejecutable:
        return {
            "estado": "error",
            "mensaje": "El parámetro 'ejecutable' es obligatorio"
        }

    # Validación 2: el archivo debe existir en disco.
    if not os.path.exists(ejecutable):
        return {
            "estado": "error",
            "mensaje": f"El ejecutable no existe: {ejecutable}"
        }

    # Validación 3: el archivo debe tener permisos de ejecución.
    # os.access(ruta, os.X_OK) le pregunta al sistema operativo:
    # "¿tengo permiso de ejecutar este archivo?"
    # os.X_OK es una constante que significa "permiso de ejecución".
    # Retorna True si tenemos permiso, False si no.
    if not os.access(ejecutable, os.X_OK):
        return {
            "estado": "error",
            "mensaje": f"El archivo no tiene permisos de ejecución: {ejecutable}"
        }

    # Validación 4: args debe ser una lista.
    # isinstance(objeto, tipo) verifica si el objeto es de ese tipo.
    if not isinstance(args, list):
        return {
            "estado": "error",
            "mensaje": "El parámetro 'args' debe ser una lista de strings"
        }

    # Validación 5: env debe ser una lista.
    if not isinstance(env, list):
        return {
            "estado": "error",
            "mensaje": "El parámetro 'env' debe ser una lista de strings"
        }

    # Generamos el identificador único para este programa.
    id_programa = generar_id(aralmac)

    # Construimos las rutas donde guardaremos los archivos.
    ruta_ejecutable_destino = os.path.join(aralmac, f"{id_programa}.ejecutable")
    ruta_meta               = os.path.join(aralmac, f"{id_programa}.meta.json")

    # Copiamos el ejecutable al directorio aralmac.
    # shutil.copy(origen, destino) copia el contenido del archivo.
    # El ejecutable copiado tendrá el nombre "p-0001.ejecutable" en aralmac.
    shutil.copy(ejecutable, ruta_ejecutable_destino)

    # En Linux, cuando copiamos un archivo, los permisos de ejecución
    # pueden perderse. Los restauramos explícitamente.
    # os.chmod() cambia los permisos de un archivo.
    # 0o755 es la notación octal de permisos en Linux:
    #   7 = rwx (lectura + escritura + ejecución) para el dueño
    #   5 = r-x (lectura + ejecución) para el grupo
    #   5 = r-x (lectura + ejecución) para otros
    os.chmod(ruta_ejecutable_destino, 0o755)

    # Guardamos los metadatos en un archivo JSON.
    # Incluimos la ruta original para referencia y los args/env.
    metadatos = {
        "id-programa": id_programa,
        "ejecutable":  ejecutable,
        "args":        args,
        "env":         env
    }

    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(metadatos, f, ensure_ascii=False, indent=2)

    return {
        "estado": "ok",
        "datos": {
            "id-programa": id_programa,
            "ejecutable":  ejecutable
        }
    }


# ─────────────────────────────────────────────
# OPERACIÓN: op_leer
# ─────────────────────────────────────────────

def op_leer(parametros, aralmac):
    """
    PROPÓSITO:
        Retorna la información completa de un programa registrado.
        Solo tiene Formato A (por id-programa).
        gesprog NO tiene "listar todos" a diferencia de gesfich.

    PARÁMETROS ESPERADOS:
        {"id-programa": "p-0001"}

    NOTA SOBRE LA MÁQUINA DE ESTADOS:
        gesprog permite Leer incluso en estado Suspendido.
        Esto lo maneja main() — op_leer() solo hace la consulta.
    """

    id_programa = parametros.get("id-programa")

    if not id_programa:
        return {
            "estado": "error",
            "mensaje": "El parámetro 'id-programa' es obligatorio"
        }

    ruta_meta = os.path.join(aralmac, f"{id_programa}.meta.json")

    # Verificamos que el programa exista en aralmac.
    if not os.path.exists(ruta_meta):
        return {
            "estado": "error",
            "mensaje": f"El programa {id_programa} no existe"
        }

    # Leemos los metadatos del archivo JSON.
    with open(ruta_meta, "r", encoding="utf-8") as f:
        metadatos = json.load(f)

    return {
        "estado": "ok",
        "datos": {
            "id-programa": metadatos["id-programa"],
            "ejecutable":  metadatos["ejecutable"],
            "args":        metadatos["args"],
            "env":         metadatos["env"]
        }
    }


# ─────────────────────────────────────────────
# OPERACIÓN: op_actualizar
# ─────────────────────────────────────────────

def op_actualizar(parametros, aralmac):
    """
    PROPÓSITO:
        Reemplaza el ejecutable almacenado con uno nuevo
        desde una ruta externa. Los metadatos (args, env)
        se mantienen igual — solo cambia el ejecutable físico.

    PARÁMETROS ESPERADOS:
        {"id-programa": "p-0001", "ruta-origen": "/home/usuario/nuevo.py"}
    """

    id_programa = parametros.get("id-programa")
    ruta_origen = parametros.get("ruta-origen")

    if not id_programa or not ruta_origen:
        return {
            "estado": "error",
            "mensaje": "Se requieren los parámetros 'id-programa' y 'ruta-origen'"
        }

    ruta_ejecutable = os.path.join(aralmac, f"{id_programa}.ejecutable")
    ruta_meta       = os.path.join(aralmac, f"{id_programa}.meta.json")

    # Verificamos que el programa destino exista en aralmac.
    if not os.path.exists(ruta_meta):
        return {
            "estado": "error",
            "mensaje": f"El programa {id_programa} no existe en aralmac"
        }

    # Verificamos que el archivo fuente exista.
    if not os.path.exists(ruta_origen):
        return {
            "estado": "error",
            "mensaje": f"El archivo fuente no existe: {ruta_origen}"
        }

    # Verificamos que el nuevo archivo sea ejecutable.
    if not os.access(ruta_origen, os.X_OK):
        return {
            "estado": "error",
            "mensaje": f"El archivo fuente no tiene permisos de ejecución: {ruta_origen}"
        }

    # Copiamos el nuevo ejecutable sobreescribiendo el anterior.
    shutil.copy(ruta_origen, ruta_ejecutable)

    # Restauramos permisos de ejecución después de copiar.
    os.chmod(ruta_ejecutable, 0o755)

    # Actualizamos también la ruta original en los metadatos.
    with open(ruta_meta, "r", encoding="utf-8") as f:
        metadatos = json.load(f)

    metadatos["ejecutable"] = ruta_origen

    with open(ruta_meta, "w", encoding="utf-8") as f:
        json.dump(metadatos, f, ensure_ascii=False, indent=2)

    return {
        "estado": "ok",
        "datos": {
            "id-programa": id_programa,
            "mensaje": "Programa actualizado correctamente"
        }
    }


# ─────────────────────────────────────────────
# OPERACIÓN: op_borrar
# ─────────────────────────────────────────────

def op_borrar(parametros, aralmac):
    """
    PROPÓSITO:
        Elimina el ejecutable y sus metadatos de aralmac.

    PARÁMETROS ESPERADOS:
        {"id-programa": "p-0001"}
    """

    id_programa = parametros.get("id-programa")

    if not id_programa:
        return {
            "estado": "error",
            "mensaje": "El parámetro 'id-programa' es obligatorio"
        }

    ruta_ejecutable = os.path.join(aralmac, f"{id_programa}.ejecutable")
    ruta_meta       = os.path.join(aralmac, f"{id_programa}.meta.json")

    if not os.path.exists(ruta_meta):
        return {
            "estado": "error",
            "mensaje": f"El programa {id_programa} no existe"
        }

    # Eliminamos tanto el ejecutable como sus metadatos.
    os.unlink(ruta_ejecutable)
    os.unlink(ruta_meta)

    return {
        "estado": "ok",
        "datos": {
            "id-programa": id_programa,
            "mensaje": "Programa eliminado correctamente"
        }
    }


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL: main
# ─────────────────────────────────────────────

def main():
    """
    PROPÓSITO:
        Punto de entrada del servicio gesprog.
        Idéntico en estructura a gesfich.main() con dos diferencias:
        1. Los flags de tubería son -p y -c (no -f y -b).
        2. La operación Leer se permite en estado Suspendido.
    """

    # ── PASO 1: Valores por defecto para las tuberías ──
    tuberia_peticiones = "/tmp/gesprog_req"
    tuberia_respuestas = "/tmp/gesprog_res"
    ruta_aralmac       = "./aralmac"

    # ── PASO 2: Leer argumentos de línea de comandos ──
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] == "-p" and i + 1 < len(args):
            # -p indica la tubería de peticiones para gesprog
            tuberia_peticiones = args[i + 1]
            i += 2
        elif args[i] == "-c" and i + 1 < len(args):
            # -c indica la tubería de respuestas para gesprog
            tuberia_respuestas = args[i + 1]
            i += 2
        elif args[i] == "-x" and i + 1 < len(args):
            # -x indica la ruta del directorio aralmac
            ruta_aralmac = args[i + 1]
            i += 2
        else:
            i += 1

    print(f"[gesprog] Iniciando...", file=sys.stderr)
    print(f"[gesprog] Tubería peticiones : {tuberia_peticiones}", file=sys.stderr)
    print(f"[gesprog] Tubería respuestas : {tuberia_respuestas}", file=sys.stderr)
    print(f"[gesprog] Directorio aralmac : {ruta_aralmac}", file=sys.stderr)

    # ── PASO 3: Crear el directorio aralmac si no existe ──
    os.makedirs(ruta_aralmac, exist_ok=True)

    # ── PASO 4: Crear las tuberías nombradas ──
    ipc.crear_tuberia(tuberia_peticiones)
    ipc.crear_tuberia(tuberia_respuestas)

    # ── PASO 5: Abrir las tuberías ──
    # Igual que en gesfich: primero lectura, luego escritura.
    # Ambas bloquean hasta que ctrllt abra el otro extremo.
    print(f"[gesprog] Esperando conexión de ctrllt...", file=sys.stderr)

    fd_peticiones = ipc.abrir_tuberia_lectura(tuberia_peticiones)
    fd_respuestas = ipc.abrir_tuberia_escritura(tuberia_respuestas)

    if fd_peticiones is None or fd_respuestas is None:
        print("[gesprog] Error al abrir tuberías. Terminando.", file=sys.stderr)
        sys.exit(1)

    print(f"[gesprog] Conectado. Esperando peticiones...", file=sys.stderr)

    # ── PASO 6: Máquina de estados ──
    estado = "Corriendo"

    # ── PASO 7: Diccionario de operaciones CRUD ──
    # NOTA: Leer NO está aquí porque tiene comportamiento especial:
    # se permite incluso en estado Suspendido.
    # Lo manejamos separado en el loop principal.
    operaciones_crud = {
        "Guardar":    lambda p: op_guardar(p, ruta_aralmac),
        "Actualizar": lambda p: op_actualizar(p, ruta_aralmac),
        "Borrar":     lambda p: op_borrar(p, ruta_aralmac),
    }

    # ── PASO 8: Loop principal ──
    while True:

        mensaje = ipc.recibir_mensaje(fd_peticiones)

        if mensaje is None:
            print("[gesprog] Tubería cerrada. Terminando.", file=sys.stderr)
            break

        operacion  = mensaje.get("operacion", "")
        parametros = mensaje.get("parametros", {})

        print(f"[gesprog] Operación recibida: {operacion}", file=sys.stderr)

        # ── Operaciones de control (siempre se procesan) ──

        if operacion == "Terminar":
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio terminado"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)
            break

        elif operacion == "Suspender":
            estado = "Suspendido"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio suspendido"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        elif operacion == "Reasumir":
            estado = "Corriendo"
            respuesta = {"estado": "ok", "datos": {"mensaje": "Servicio reasumido"}}
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        # ── Leer: se permite en cualquier estado ──
        # Esta es la diferencia clave con gesfich.
        # El profe especificó que gesprog permite Leer
        # incluso estando Suspendido (ver máquina de estados).
        elif operacion == "Leer":
            respuesta = op_leer(parametros, ruta_aralmac)
            ipc.enviar_mensaje(fd_respuestas, respuesta)

        # ── Operaciones CRUD (solo en estado Corriendo) ──
        elif operacion in operaciones_crud:

            if estado == "Suspendido":
                respuesta = {
                    "estado": "error",
                    "mensaje": "Servicio suspendido. No acepta esta operación."
                }
            else:
                funcion   = operaciones_crud[operacion]
                respuesta = funcion(parametros)

            ipc.enviar_mensaje(fd_respuestas, respuesta)

        else:
            respuesta = {
                "estado": "error",
                "mensaje": f"Operación desconocida: {operacion}"
            }
            ipc.enviar_mensaje(fd_respuestas, respuesta)

    # ── PASO 9: Limpieza al terminar ──
    print("[gesprog] Cerrando y limpiando recursos...", file=sys.stderr)
    ipc.cerrar_tuberia(fd_peticiones, tuberia_peticiones)
    ipc.cerrar_tuberia(fd_respuestas, tuberia_respuestas)
    print("[gesprog] Servicio terminado.", file=sys.stderr)


# ─────────────────────────────────────────────
# PUNTO DE ENTRADA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    main()
