"""
Paquete de la Lambda de entrada.

Este __init__.py NO es opcional: sin el, Python no puede importar
"lambda.handler" como modulo, y AWS Lambda (que busca el handler en la raiz
del zip) fallaria con ModuleNotFoundError en la primera invocacion.

Ojo: "lambda" es tambien el nombre de un modulo de la stdlib de Python
(_thread / functools usan internamente el termino), pero como paquete de
primer nivel en el zip no hay conflicto: Lambda ejecuta el handler con
/var/task como raiz del sys.path.

No borres este fichero. Ver DEPLOY.md, seccion "Problemas frecuentes".
"""
