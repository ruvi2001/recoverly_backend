@echo off
REM Windows batch script to run all services in development mode

echo ========================================
echo Starting Recoverly Platform Services
echo ========================================

REM Check if virtual environment exists
if not exist ".venv\" (
    echo Error: Virtual environment not found!
    echo Please run: python -m venv .venv
    exit /b 1
)

REM Activate virtual environment
call .venv\Scripts\activate

REM Check if database is running
echo.
echo Checking database connection...
python -c "import psycopg2; from shared.core.settings import settings; psycopg2.connect(host=settings.DB_HOST, port=settings.DB_PORT, database=settings.DB_NAME, user=settings.DB_USER, password=settings.DB_PASSWORD); print('✓ Database connected')" 2>nul
if errorlevel 1 (
    echo ✗ Database connection failed!
    echo Please ensure PostgreSQL is running and .env is configured
    exit /b 1
)

echo.
echo ========================================
echo Starting Services...
echo ========================================

REM Start Social Service (Component 3)
echo.
echo [1/4] Starting Social Service on port 8003...
start "Social Service" cmd /k "cd services\social_service && python app\main.py"
timeout /t 2 /nobreak >nul

REM Start Risk Service (Component 1) - if implemented
if exist "services\risk_service\app\main.py" (
    echo [2/4] Starting Risk Service on port 8001...
    start "Risk Service" cmd /k "cd services\risk_service && python app\main.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [2/4] Risk Service not implemented yet - skipping
)

REM Start Reco Service (Component 2) - if implemented
if exist "services\reco_service\app\main.py" (
    echo [3/4] Starting Reco Service on port 8002...
    start "Reco Service" cmd /k "cd services\reco_service && python app\main.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [3/4] Reco Service not implemented yet - skipping
)

REM Start Causal Service (Component 4) - if implemented
if exist "services\causal_service\app\main.py" (
    echo [4/4] Starting Causal Service on port 8004...
    start "Causal Service" cmd /k "cd services\causal_service && python app\main.py"
    timeout /t 2 /nobreak >nul
) else (
    echo [4/4] Causal Service not implemented yet - skipping
)

echo.
echo ========================================
echo All services started!
echo ========================================
echo.
echo Service URLs:
echo   Social Service: http://localhost:8003
echo   Risk Service:   http://localhost:8001
echo   Reco Service:   http://localhost:8002
echo   Causal Service: http://localhost:8004
echo.
echo Press Ctrl+C in each window to stop services
echo ========================================

pause
