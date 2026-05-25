#!/bin/bash
# prueba_ok.sh — Script simple para probar el ejecutor
#
# PROPÓSITO:
#   Este script es el programa más simple posible para probar
#   que el ejecutor funciona de extremo a extremo.
#   Lee de stdin y escribe en stdout — el modelo exacto de
#   proceso de lotes que describe el proyecto.
#
# QUÉ HACE:
#   1. Imprime un mensaje de inicio
#   2. Lee todo lo que venga de stdin
#   3. Lo imprime en stdout con un prefijo
#   4. Termina con código de salida 0 (éxito)
#
# POR QUÉ CÓDIGO DE SALIDA 0 ES IMPORTANTE:
#   El ejecutor usa waitpid() para saber si el proceso terminó bien.
#   os.WEXITSTATUS() lee el código de salida.
#   Si es 0 → estado "terminado"
#   Si es distinto de 0 → estado "error"
#   Este script siempre termina con 0.

echo "=== prueba_ok.sh iniciado ==="

# 'cat' lee todo el stdin y lo imprime en stdout.
# Como ya redirigimos stdin al fichero de entrada en el ejecutor,
# cat leerá el contenido de ese fichero.
cat

echo "=== prueba_ok.sh terminado ==="

# En bash, el código de salida del script es el del último comando.
# Como echo siempre termina con 0, este script también termina con 0.
# Podemos ser explícitos con:
exit 0
