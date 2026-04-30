# PropScore Deployment Checklist

## Pre-Deployment (Local Development)

### System Setup
- [ ] **Ollama installed** and running on localhost:11434
  - [ ] Qwen2-VL 7B model pulled (5GB)
  - [ ] Llama 3.1 8B model pulled (4GB)
  - [ ] Nomic-embed-text model pulled (274MB)
  - Verify: `curl http://localhost:11434/api/tags`

- [ ] **PostgreSQL installed and running** on localhost:5432
  - [ ] Database `propscore` created
  - [ ] User `propscore` created with password `propscore`
  - [ ] All privileges granted
  - Verify: `psql -U propscore -d propscore -c "SELECT 1"`

- [ ] **Python 3.11+** installed
  - [ ] Virtual environment created: `backend/venv`
  - [ ] All requirements installed: `pip install -r requirements-prod.txt`
  - Verify: `python -c "import fastapi; print('OK')"`

### Backend Initialization
- [ ] Database tables created
  ```bash
  python
  >>> from backend.database import Base, get_db_engine
  >>> engine = get_db_engine("postgresql://propscore:propscore@localhost/propscore")
  >>> Base.metadata.create_all(bind=engine)
  ```

- [ ] Backend server starts without errors
  ```bash
  python -m uvicorn backend.main:app --reload
  # Should show: Uvicorn running on http://0.0.0.0:8000
  ```

- [ ] API health check passes
  ```bash
  curl http://localhost:8000/health
  # Should return: {"status": "healthy", "ollama_available": true, ...}
  ```

### Data Preparation
- [ ] **Circle rates data loaded**
  - [ ] File `backend/data/circle_rates.csv` prepared
  - [ ] Contains at least 10 records (pincode, property_type, city, rate_per_sqft)
  - [ ] Data loaded via: `pipeline.load_circle_rates(db, source_file=...)`
  - Verify: Database has CircleRate records

- [ ] **Listing statistics aggregated**
  - [ ] File `backend/data/listings.csv` prepared with 1000+ listings
  - [ ] Data aggregated: `pipeline.aggregate_listing_statistics(db)`
  - Verify: ListingStats table populated

- [ ] **IPI grid pre-computed**
  - [ ] `pipeline.precompute_ipi_grid(db)` executed
  - [ ] At least 1000 grid points computed
  - Verify: IPICache table has records

- [ ] **Data setup report verified**
  ```bash
  python
  >>> from backend.data_pipeline import DataPipeline
  >>> pipeline = DataPipeline()
  >>> report = pipeline.generate_setup_report(db)
  # All counts should be > 0
  ```

### Frontend Integration
- [ ] **Environment configured**
  - [ ] File `frontend/.env.local` created with `VITE_API_URL=http://localhost:8000`

- [ ] **API client wired up**
  - [ ] `src/lib/api.js` properly imported in components
  - [ ] No hardcoded demo data in InputWizard/Dashboard
  - [ ] Real API calls on form submission

- [ ] **Frontend runs without errors**
  ```bash
  npm run dev
  # Should show: Local: http://localhost:5173
  ```

### End-to-End Testing
- [ ] **Health check test**
  ```bash
  curl http://localhost:8000/health
  # All components green
  ```

- [ ] **Form submission test**
  - [ ] Fill form with test property data
  - [ ] Click "Run Valuation"
  - [ ] Backend processes (show logs)
  - [ ] Results appear on frontend

- [ ] **Performance check**
  - [ ] Valuation completes in 5-10 seconds (first run slower due to model loading)
  - [ ] GPU utilization shows >85% during inference
  - [ ] No errors in browser console or backend logs

---

## Production Deployment

### Pre-Deployment Verification
- [ ] **Hardware requirements met**
  - [ ] NVIDIA GPU with 8GB+ VRAM (RTX 4070, RTX 5050, etc)
  - [ ] 16GB+ system RAM
  - [ ] 50GB+ free disk space
  - [ ] Stable internet (for initial model downloads)

- [ ] **Security review**
  - [ ] PostgreSQL password changed from default
  - [ ] API endpoints require authentication (if multi-user)
  - [ ] HTTPS configured (if internet-facing)
  - [ ] Network policies restrict access to port 8000

- [ ] **Backup strategy**
  - [ ] PostgreSQL daily backups configured
  - [ ] Ollama model cache backed up
  - [ ] Circle rate data versioned

### Docker Deployment Option
- [ ] **Docker installed** on deployment server
  - [ ] NVIDIA Container Runtime installed
  - [ ] `nvidia-docker run --gpus all ubuntu` works

- [ ] **Docker images built**
  ```bash
  docker build -t propscore:latest .
  # Build completes without errors
  ```

- [ ] **Docker compose configured**
  - [ ] `docker-compose.yml` reviewed and customized
  - [ ] Database credentials changed from defaults
  - [ ] Volume mounts point to correct directories

- [ ] **Docker containers start successfully**
  ```bash
  docker-compose up -d
  docker-compose ps
  # All containers "Up"
  ```

### Native Installation Option
- [ ] **Dependencies installed on production server**
  - [ ] PostgreSQL server running
  - [ ] Ollama service configured to auto-start
  - [ ] Python 3.11+ installed

- [ ] **Backend deployed**
  - [ ] Source code copied to `/opt/propscore`
  - [ ] Virtual environment created
  - [ ] Systemd service created for auto-restart
  - [ ] Systemd service tested: `systemctl status propscore-backend`

- [ ] **Frontend deployed**
  - [ ] Built frontend copied to web root
  - [ ] Nginx/Apache configured as reverse proxy
  - [ ] SSL certificate installed (if internet-facing)

### Post-Deployment Verification
- [ ] **All services running**
  ```bash
  # Check each service
  curl http://server:8000/health
  curl http://server:3000
  curl http://server:11434/api/tags
  ```

- [ ] **Database connectivity**
  - [ ] Can connect to PostgreSQL
  - [ ] All tables created and populated
  - [ ] Backups running on schedule

- [ ] **Performance baseline**
  - [ ] Average valuation time: 4-8 seconds
  - [ ] GPU utilization: 80-95%
  - [ ] Database query times: <100ms
  - [ ] Memory usage: <4GB

- [ ] **Error monitoring**
  - [ ] Logs being written to appropriate location
  - [ ] Error rate: <0.1% for valid requests
  - [ ] Timeout errors: 0% (or <1% acceptable)

- [ ] **User testing**
  - [ ] Internal team can submit properties successfully
  - [ ] Results make business sense
  - [ ] Fraud detection flags work correctly
  - [ ] Report exports work (if implemented)

---

## Operational Checklist (Monthly)

- [ ] **GPU health check**
  ```bash
  nvidia-smi
  # Check temperatures, memory, processes
  ```

- [ ] **Database maintenance**
  - [ ] Backup verified and tested
  - [ ] Dead tuples cleaned (VACUUM)
  - [ ] Query performance still good (check slow logs)

- [ ] **Data freshness**
  - [ ] Circle rates still current (within 3 months)
  - [ ] Listing data updated if scraped
  - [ ] IPI cache refreshed if locations changed

- [ ] **Model updates**
  - [ ] Check for updated model versions
  - [ ] Test new versions before production deployment
  - [ ] Keep models in sync across fleet if multi-server

- [ ] **Performance trend**
  - [ ] Average valuation time stable?
  - [ ] No performance degradation?
  - [ ] Concurrent request handling OK?

---

## Troubleshooting Reference

| Issue | Symptom | Solution |
|-------|---------|----------|
| Ollama not running | `Connection refused: 11434` | Start Ollama service |
| Out of CUDA memory | `CUDA out of memory` | Switch to quantized models (Q4/Q8) |
| Database connection fails | `FATAL: role "propscore" does not exist` | Create user and database |
| Slow inference | Valuation takes >30s | Check GPU utilization, verify model loaded |
| Model downloading repeatedly | Ollama re-downloads models each startup | Set `OLLAMA_KEEP_ALIVE=24h` |
| Frontend can't reach backend | API errors in console | Check CORS, firewall, API_URL config |
| High memory usage | System becomes slow | Reduce max_workers or increase RAM |

---

## Sign-Off

- [ ] **Development**: All tests passing, performance good
- [ ] **Staging**: End-to-end test successful, data loaded
- [ ] **Production**: Deployed, health checks green, monitoring active
- [ ] **UAT**: Internal team verified, results correct
- [ ] **Go-Live**: Ready for real NBFC deployment

**Deployment Date**: ___________
**Deployed By**: ___________
**Verified By**: ___________

---

## Contact & Support

For issues or questions:
1. Check logs: `docker-compose logs -f` or tail system logs
2. Verify health: `curl http://localhost:8000/health`
3. Check database: Connect via `psql` or pgAdmin
4. Monitor GPU: `nvidia-smi` or `nvidia-smi -l 1`

---

**System is production-ready when all checkboxes are checked ✓**
