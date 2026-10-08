#!/usr/bin/env bash

echo "======================================================="
echo "   Iniciando Kiosco de Pedidos por Voz con IA"
echo "======================================================="
echo ""

# 1. Comprobar Python
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python no está instalado."
    echo "Por favor instálalo desde tu gestor de paquetes o https://www.python.org/"
    exit 1
fi

# 2. Comprobar Ollama
if command -v ollama &>/dev/null; then
    echo "[OK] Ollama detectado."
    # Comprobar si el modelo existe
    if ! ollama list | grep -q "llama3.2:1b"; then
        echo "[INFO] Descargando modelo llama3.2:1b (solo se realiza la primera vez)..."
        ollama pull llama3.2:1b
    else
        echo "[OK] Modelo llama3.2:1b disponible."
    fi
else
    echo "[ALERTA] Ollama no se detectó en el sistema."
    echo "Para que las funciones de IA respondan, descarga e instala Ollama desde https://ollama.com/"
    echo ""
fi

# 3. Entorno virtual
if [ ! -d "venv" ]; then
    echo "[INFO] Creando entorno virtual de Python (venv)..."
    $PYTHON_CMD -m venv venv
fi

# 4. Activar entorno virtual
source venv/bin/activate

# 5. Instalar o validar dependencias
echo "[INFO] Verificando dependencias en requirements.txt..."
pip install -r requirements.txt --quiet --disable-pip-version-check

# 6. Abrir navegador automáticamente si está disponible
(sleep 2 && {
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:8000" &>/dev/null
    elif command -v open &>/dev/null; then
        open "http://localhost:8000" &>/dev/null
    fi
}) &

# 7. Iniciar servidor FastAPI
echo ""
echo "======================================================="
echo "   Kiosco de Autoservicio:  http://localhost:8000"
echo "   Panel de Administración: http://localhost:8000/admin"
echo "   Presiona CTRL+C para detener el servicio."
echo "======================================================="
echo ""
uvicorn main:app --host 0.0.0.0 --port 8000
