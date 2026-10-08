@echo off
chcp 65001 >nul
title Kiosco de Pedidos por Voz con IA

echo =======================================================
echo   Iniciando Kiosco de Pedidos por Voz con IA
echo =======================================================
echo.

:: 1. Comprobar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no está instalado o no está en el PATH.
    echo Por favor descarga e instala Python desde: https://www.python.org/
    echo Asegúrate de marcar la casilla "Add Python to PATH" durante la instalación.
    pause
    exit /b 1
)

:: 2. Comprobar Ollama
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ALERTA] No se detectó Ollama instalado en el sistema.
    echo Para que la IA funcione, instala Ollama desde: https://ollama.com/
    echo.
) else (
    echo [OK] Ollama detectado. Verificando modelo 'llama3.2:1b'...
    ollama list | findstr "llama3.2:1b" >nul 2>&1
    if %errorlevel% neq 0 (
        echo [INFO] Descargando modelo llama3.2:1b (solo se hace la primera vez)...
        ollama pull llama3.2:1b
    ) else (
        echo [OK] Modelo llama3.2:1b ya disponible.
    )
)

:: 3. Entorno virtual
if not exist "venv" (
    echo [INFO] Creando entorno virtual de Python (venv)...
    python -m venv venv
)

:: 4. Activar entorno virtual
call venv\Scripts\activate

:: 5. Instalar/Actualizar dependencias
echo [INFO] Verificando dependencias necesarias...
pip install -r requirements.txt --quiet --disable-pip-version-check

:: 6. Abrir navegador automáticamente tras 2 segundos
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: 7. Iniciar servidor FastAPI
echo.
echo =======================================================
echo   Kiosco de Autoservicio:  http://localhost:8000
echo   Panel de Administracion: http://localhost:8000/admin
echo   Presiona CTRL+C para detener el servicio.
echo =======================================================
echo.
uvicorn main:app --host 0.0.0.0 --port 8000

pause
