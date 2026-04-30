from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import asyncio
import uuid
from datetime import datetime
from loguru import logger
import os

from config import settings
from database import Property, Valuation, FraudCheck, PropertyImage, get_db
from pipeline_dag import PipelineDAG, geo_enrichment_task, circle_rate_task, ipi_compute_task, market_signals_task, vision_analysis_task, fraud_detection_task, xgboost_multiplier_task, narrative_generation_task
from websocket_progress import router as progress_router, ProgressTracker

# ============================================================================
# Request/Response Models
# ============================================================================

class PropertyInput(BaseModel):
    """Initial property input from frontend"""
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    property_type: str  # apartment, house, etc
    config: Optional[str] = None  # 2BHK, 3BHK
    carpet_area: float
    age_bucket: Optional[str] = None
    occupancy_status: Optional[str] = None
    legal_status: Optional[str] = None
    pincode: str
    city: str
    images: Optional[List[str]] = None

class ValuationResponse(BaseModel):
    """Valuation response to frontend"""
    property_id: str
    market_value: str
    distress_value: str
    propScore: float
    confidence_score: float
    confidence_breakdown: Dict[str, float]
    time_to_sell: str
    risk_level: str
    narrative: str
    fraud_flags: List[Dict[str, Any]]
    pipeline_execution_time: float

# ============================================================================
# FastAPI Setup
# ============================================================================

app = FastAPI(
    title="PropScore Backend",
    description="Production-grade property valuation engine",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include WebSocket progress router
app.include_router(progress_router)

# Database
from database import engine, Base, SessionLocal

# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "ollama_available": check_ollama_available(),
        "database_available": check_database_available(SessionLocal()),
        "models_loaded": check_models_loaded()
    }

def check_ollama_available() -> bool:
    """Check if Ollama is running"""
    try:
        import requests
        resp = requests.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=2)
        return resp.status_code == 200
    except:
        return False

def check_database_available(session) -> bool:
    """Check if database is accessible"""
    try:
        session.execute("SELECT 1")
        return True
    except:
        return False

def check_models_loaded() -> bool:
    """Check if models are pre-loaded"""
    # TODO: Implement model pre-loading check
    return True

# ============================================================================
# Main Valuation Endpoint
# ============================================================================

@app.post("/valuate", response_model=ValuationResponse)
async def run_valuation(
    property_input: PropertyInput,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Main valuation endpoint
    
    Accepts property details, runs full parallel inference pipeline,
    returns valuation + fraud flags + confidence scores
    """
    logger.info(f"Valuation request received for {property_input.address}")
    
    try:
        # 1. Store property in database
        property_record = Property(
            address=property_input.address,
            latitude=property_input.latitude,
            longitude=property_input.longitude,
            property_type=property_input.property_type,
            config=property_input.config,
            carpet_area=property_input.carpet_area,
            age_bucket=property_input.age_bucket,
            pincode=property_input.pincode,
            city=property_input.city,
            status="submitted"
        )
        db.add(property_record)
        db.commit()
        db.refresh(property_record)
        
        logger.info(f"Property stored with ID: {property_record.id}")
        
        # 2. Build and execute parallel pipeline
        pipeline = build_pipeline(
            property_record.id,
            property_input,
            db
        )
        
        pipeline_results = await pipeline.execute()
        
        # 3. Aggregate results into valuation
        valuation = aggregate_results(
            property_record.id,
            property_input,
            pipeline_results,
            db
        )
        
        # 4. Store fraud flags
        fraud_flags = store_fraud_flags(
            property_record.id,
            valuation.id,
            pipeline_results,
            db
        )
        
        logger.info(f"Valuation completed: {valuation.id}")
        
        return ValuationResponse(
            property_id=property_record.id,
            market_value=valuation.market_value,
            distress_value=valuation.distress_value,
            propScore=valuation.propScore,
            confidence_score=valuation.confidence_score,
            confidence_breakdown=valuation.confidence_breakdown,
            time_to_sell=valuation.time_to_sell,
            risk_level=fraud_flags.risk_level,
            narrative=pipeline_results["tasks"]["narrative_generation"]["result"]["executive_summary"],
            fraud_flags=[],  # TODO: Format fraud flags
            pipeline_execution_time=pipeline_results["total_execution_time"]
        )
        
    except Exception as e:
        logger.error(f"Valuation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Helper Functions
# ============================================================================

def build_pipeline(property_id: str, prop_input: PropertyInput, db: Session) -> PipelineDAG:
    """
    Build the parallel inference DAG
    
    Task graph:
    - geo_enrichment (independent)
    - circle_rate (independent)
    - ipi_compute (depends: geo_enrichment)
    - market_signals (independent)
    - vision_analysis (depends: images)
    - fraud_detection (depends: vision_analysis, circle_rate)
    - xgboost_multiplier (depends: market_signals, ipi_compute)
    - narrative_generation (depends: ALL OTHERS)
    """
    
    # Create progress tracker for this valuation
    progress_tracker = ProgressTracker(property_id)
    
    dag = PipelineDAG(max_workers=settings.MAX_WORKERS, progress_tracker=progress_tracker)
    
    # Input context
    input_context = {
        "property_id": property_id,
        "address": prop_input.address,
        "property_type": prop_input.property_type,
        "config": prop_input.config,
        "carpet_area": prop_input.carpet_area,
        "age_bucket": prop_input.age_bucket,
        "pincode": prop_input.pincode,
        "city": prop_input.city,
        "has_images": bool(prop_input.images),
        "images": prop_input.images or [],
    }
    
    # Add tasks in dependency order
    dag.add_task(
        "geo_enrichment",
        lambda ctx: geo_enrichment_task(ctx),
        dependencies=[],
        timeout=10
    )
    
    dag.add_task(
        "circle_rate",
        lambda ctx: circle_rate_task(ctx),
        dependencies=[],
        timeout=5
    )
    
    dag.add_task(
        "ipi_compute",
        lambda ctx: ipi_compute_task(ctx),
        dependencies=["geo_enrichment"],
        timeout=15
    )
    
    dag.add_task(
        "market_signals",
        lambda ctx: market_signals_task(ctx),
        dependencies=[],
        timeout=10
    )
    
    dag.add_task(
        "vision_analysis",
        lambda ctx: vision_analysis_task(ctx),
        dependencies=[],
        timeout=60  # VLM takes time
    )
    
    dag.add_task(
        "fraud_detection",
        lambda ctx: fraud_detection_task(ctx),
        dependencies=["vision_analysis", "circle_rate"],
        timeout=30
    )
    
    dag.add_task(
        "xgboost_multiplier",
        lambda ctx: xgboost_multiplier_task(ctx),
        dependencies=["market_signals", "ipi_compute"],
        timeout=10
    )
    
    dag.add_task(
        "narrative_generation",
        lambda ctx: narrative_generation_task(ctx),
        dependencies=["geo_enrichment", "circle_rate", "ipi_compute", "market_signals", "vision_analysis", "fraud_detection", "xgboost_multiplier"],
        timeout=30
    )
    
    return dag

def aggregate_results(
    property_id: str,
    prop_input: PropertyInput,
    pipeline_results: Dict[str, Any],
    db: Session
) -> Valuation:
    """Aggregate parallel task results into final valuation"""
    
    tasks = pipeline_results["tasks"]
    
    # Extract key results
    circle_rate = tasks["circle_rate"]["result"]["circle_rate"]
    xgb_multiplier = tasks["xgboost_multiplier"]["result"]["market_multiplier"]
    vision = tasks["vision_analysis"]["result"]
    market = tasks["market_signals"]["result"]
    ipi = tasks["ipi_compute"]["result"]
    
    # Calculate valuations
    base_value = circle_rate * prop_input.carpet_area
    market_value = base_value * xgb_multiplier
    distress_value = market_value * 0.80  # 20% discount
    
    # Calculate confidence
    confidence = calculate_confidence(vision, prop_input)
    
    # Create valuation record
    valuation = Valuation(
        property_id=property_id,
        market_value=format_currency(market_value),
        distress_value=format_currency(distress_value),
        propScore=calculate_propscore(market, circle_rate, vision),
        confidence_score=confidence,
        confidence_breakdown={
            "base": 0.6,
            "legal": 0.15,
            "visual": 0.15 if vision["has_images"] else 0,
            "historical": 0.1
        },
        circle_rate=circle_rate,
        market_multiplier=xgb_multiplier,
        time_to_sell="45-60 days",
        pipeline_execution_time=pipeline_results["total_execution_time"],
        has_images=vision["has_images"],
        raw_output=pipeline_results
    )
    
    db.add(valuation)
    db.commit()
    db.refresh(valuation)
    
    return valuation

def calculate_confidence(vision: Dict, prop_input: PropertyInput) -> float:
    """Calculate confidence score based on available data"""
    confidence = 0.55  # Base
    
    if vision.get("has_images"):
        confidence += 0.15
    
    if prop_input.age_bucket:
        confidence += 0.05
    
    if prop_input.legal_status == "clear":
        confidence += 0.05
    
    return min(0.95, confidence)

def calculate_propscore(market: Dict, circle_rate: float, vision: Dict) -> float:
    """Calculate PropScore (0-100)"""
    # Formula: based on market demand, supply, location quality
    base = 50
    
    if market.get("demand_proxy", 0) > 0.7:
        base += 15
    
    if market.get("listing_density", 0) > 0.8:
        base += 10
    
    if vision.get("condition_score", 5) >= 7:
        base += 10
    
    return min(100, max(0, base))

def format_currency(value: float) -> str:
    """Format value as ₹ currency"""
    if value >= 1e7:  # >= 1 Cr
        return f"₹{value/1e7:.1f} Cr"
    elif value >= 1e5:  # >= 1 Lakh
        return f"₹{value/1e5:.1f} Lakh"
    else:
        return f"₹{value:,.0f}"

def store_fraud_flags(
    property_id: str,
    valuation_id: str,
    pipeline_results: Dict,
    db: Session
) -> FraudCheck:
    """Store fraud detection results"""
    
    fraud = pipeline_results["tasks"]["fraud_detection"]["result"]
    
    fraud_record = FraudCheck(
        property_id=property_id,
        valuation_id=valuation_id,
        phash_flag=fraud.get("phash_flag", False),
        phash_score=fraud.get("phash_score"),
        clip_similarity=fraud.get("clip_similarity"),
        clip_flag=fraud.get("clip_similarity", 0) > 0.85,
        listing_photo_detected=fraud.get("listing_photo_detected", False),
        size_sanity_pass=fraud.get("size_sanity_pass", True),
        location_consistency_score=fraud.get("location_consistency"),
        location_consistency_flag=fraud.get("location_consistency", 1.0) < 0.70,
        risk_level=fraud.get("risk_level", "low"),
        all_flags=fraud.get("flags", [])
    )
    
    db.add(fraud_record)
    db.commit()
    
    return fraud_record

# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("PropScore backend starting up")
    
    # Create tables
    from database import Base
    Base.metadata.create_all(bind=engine)
    
    logger.info("Database tables created")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
