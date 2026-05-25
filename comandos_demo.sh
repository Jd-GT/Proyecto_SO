#!/bin/bash
# comandos_demo.sh — Guión de demostración para la sustentación
#
# INSTRUCCIONES DE USO:
#   NO ejecutes este archivo directamente.
#   Úsalo como guión — copia y pega cada sección en la terminal correcta.
#
# TERMINALES NECESARIAS (ábrelas antes de empezar):
#   T1 → gesfich
#   T2 → gesprog
#   T3 → ejecutor
#   T4 → ctrllt
#   T5 → cliente escritor (donde envías peticiones)
#   T6 → cliente lector   (donde ves respuestas)

# ═══════════════════════════════════════════════════════
# PASO 0 — PREPARACIÓN (hacer ANTES de la sustentación)
# ═══════════════════════════════════════════════════════

# En cualquier terminal — limpiar tuberías anteriores:
rm -f /tmp/cliente_req /tmp/cliente_res
rm -f /tmp/gesfich_req /tmp/gesfich_res
rm -f /tmp/gesprog_req /tmp/gesprog_res
rm -f /tmp/ejecutor_req /tmp/ejecutor_res

# Crear directorio aralmac si no existe:
mkdir -p ./aralmac

# Copiar prueba_ok.sh al directorio del proyecto y darle permisos:
chmod +x ./prueba_ok.sh

# ═══════════════════════════════════════════════════════
# PASO 1 — ARRANCAR SERVICIOS (cada uno en su terminal)
# ═══════════════════════════════════════════════════════

# T1 — gesfich:
python3 gesfich.py -f /tmp/gesfich_req -b /tmp/gesfich_res -x ./aralmac

# T2 — gesprog:
python3 gesprog.py -p /tmp/gesprog_req -c /tmp/gesprog_res -x ./aralmac

# T3 — ejecutor:
python3 ejecutor.py -e /tmp/ejecutor_req -d /tmp/ejecutor_res -x ./aralmac

# T4 — ctrllt (arranca de último porque conecta con todos):
python3 ctrllt.py \
  -c /tmp/cliente_req -a /tmp/cliente_res \
  -f /tmp/gesfich_req -b /tmp/gesfich_res \
  -p /tmp/gesprog_req -g /tmp/gesprog_res \
  -e /tmp/ejecutor_req -d /tmp/ejecutor_res

# ═══════════════════════════════════════════════════════
# PASO 2 — CONECTAR CLIENTE
# ═══════════════════════════════════════════════════════

# T6 — abrir lector de respuestas (ejecutar primero):
cat /tmp/cliente_res

# T5 — abrir escritor de peticiones:
exec 3>/tmp/cliente_req

# ═══════════════════════════════════════════════════════
# PASO 3 — DEMO gesfich (ejecutar en T5)
# ═══════════════════════════════════════════════════════

# Crear fichero de entrada:
echo '{"servicio":"gesfich","operacion":"Crear","parametros":{"nombre":"entrada.txt"}}' >&3

# Crear fichero de salida:
echo '{"servicio":"gesfich","operacion":"Crear","parametros":{"nombre":"salida.txt"}}' >&3

# Escribir contenido en el fichero de entrada:
# (en cualquier terminal libre)
echo "Hola desde el fichero de entrada" > ./aralmac/f-0001.txt

# Leer el fichero de entrada para verificar:
echo '{"servicio":"gesfich","operacion":"Leer","parametros":{"id-fichero":"f-0001"}}' >&3

# Listar todos los ficheros:
echo '{"servicio":"gesfich","operacion":"Leer","parametros":{}}' >&3

# ═══════════════════════════════════════════════════════
# PASO 4 — DEMO gesprog (ejecutar en T5)
# ═══════════════════════════════════════════════════════

# Registrar prueba_ok.sh como programa:
echo '{"servicio":"gesprog","operacion":"Guardar","parametros":{"ejecutable":"./prueba_ok.sh","args":[],"env":[]}}' >&3

# Leer el programa registrado:
echo '{"servicio":"gesprog","operacion":"Leer","parametros":{"id-programa":"p-0001"}}' >&3

# ═══════════════════════════════════════════════════════
# PASO 5 — DEMO ejecutor (ejecutar en T5)
# ═══════════════════════════════════════════════════════

# Ejecutar el lote (f-0001 → p-0001 → f-0002):
echo '{"servicio":"ejecutor","operacion":"Ejecutar","parametros":{"id-programa":"p-0001","stdin":"f-0001","stdout":"f-0002"}}' >&3

# Esperar 1 segundo y consultar estado:
echo '{"servicio":"ejecutor","operacion":"Estado","parametros":{}}' >&3

# Leer el resultado en el fichero de salida:
echo '{"servicio":"gesfich","operacion":"Leer","parametros":{"id-fichero":"f-0002"}}' >&3

# ═══════════════════════════════════════════════════════
# PASO 6 — DEMO máquina de estados (ejecutar en T5)
# ═══════════════════════════════════════════════════════

# Suspender gesfich:
echo '{"servicio":"gesfich","operacion":"Suspender","parametros":{}}' >&3

# Intentar Crear mientras está suspendido (debe dar error):
echo '{"servicio":"gesfich","operacion":"Crear","parametros":{"nombre":"falla.txt"}}' >&3

# Reanudar gesfich:
echo '{"servicio":"gesfich","operacion":"Reasumir","parametros":{}}' >&3

# Crear ahora sí funciona:
echo '{"servicio":"gesfich","operacion":"Crear","parametros":{"nombre":"despues_reasumir.txt"}}' >&3

# ═══════════════════════════════════════════════════════
# PASO 7 — TERMINAR EL SISTEMA (ejecutar en T5)
# ═══════════════════════════════════════════════════════

# Terminar ctrllt (suspende todos los servicios):
echo '{"operacion":"Terminar","parametros":{}}' >&3
