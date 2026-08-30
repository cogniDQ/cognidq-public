# Run Database Migrations
# Execute this script to set up authentication tables

Write-Host "Starting database migration..." -ForegroundColor Green

# Check if Docker is running
$dockerRunning = docker ps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Check if containers are running
Write-Host "Checking if containers are running..." -ForegroundColor Yellow
docker-compose ps

# Run migrations
Write-Host "`nRunning database migrations..." -ForegroundColor Yellow
docker-compose exec backend alembic upgrade head

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✓ Migration completed successfully!" -ForegroundColor Green
    Write-Host "`nYou can now:" -ForegroundColor Cyan
    Write-Host "  1. Access the app at http://localhost:5173" -ForegroundColor White
    Write-Host "  2. View API docs at http://localhost:8000/docs" -ForegroundColor White
    Write-Host "  3. Register a new user and test authentication" -ForegroundColor White
} else {
    Write-Host "`n✗ Migration failed. Check the error messages above." -ForegroundColor Red
    Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Make sure all containers are running: docker-compose ps" -ForegroundColor White
    Write-Host "  2. Check database logs: docker-compose logs db" -ForegroundColor White
    Write-Host "  3. Restart containers: docker-compose restart" -ForegroundColor White
}
