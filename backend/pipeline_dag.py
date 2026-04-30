import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from loguru import logger
import concurrent.futures
from abc import ABC, abstractmethod

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class PipelineTask:
    """Single task in the inference pipeline"""
    name: str
    func: Callable
    dependencies: List[str] = field(default_factory=list)
    is_async: bool = False
    timeout: Optional[float] = None
    retry_count: int = 3
    
    status: TaskStatus = TaskStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    
    @property
    def execution_time(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

class PipelineDAG:
    """
    Directed Acyclic Graph for parallel inference pipeline
    
    Tasks run in parallel when they have no dependencies.
    Only waits for actual task dependencies, not sequential execution.
    """
    
    def __init__(self, max_workers: int = 4, progress_tracker=None):
        self.tasks: Dict[str, PipelineTask] = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.loop = asyncio.new_event_loop()
        self._dependency_graph: Dict[str, set] = {}
        self.progress_tracker = progress_tracker  # Optional progress tracking
        
        
    def add_task(
        self,
        name: str,
        func: Callable,
        dependencies: Optional[List[str]] = None,
        is_async: bool = False,
        timeout: Optional[float] = None
    ):
        """Add a task to the DAG"""
        if name in self.tasks:
            raise ValueError(f"Task {name} already exists")
        
        task = PipelineTask(
            name=name,
            func=func,
            dependencies=dependencies or [],
            is_async=is_async,
            timeout=timeout
        )
        
        self.tasks[name] = task
        self._dependency_graph[name] = set(dependencies or [])
        
        logger.info(f"Added task '{name}' with dependencies {task.dependencies}")
        
    def _get_ready_tasks(self) -> List[str]:
        """Get all tasks whose dependencies are satisfied"""
        ready = []
        for name, task in self.tasks.items():
            if task.status == TaskStatus.PENDING:
                # Check if all dependencies are completed
                deps_satisfied = all(
                    self.tasks[dep].status == TaskStatus.COMPLETED 
                    for dep in task.dependencies
                )
                if deps_satisfied:
                    ready.append(name)
        return ready
    
    def _get_context(self) -> Dict[str, Any]:
        """Get current pipeline context (results from all completed tasks)"""
        return {
            name: task.result
            for name, task in self.tasks.items()
            if task.status == TaskStatus.COMPLETED
        }
    
    async def _run_task(self, task: PipelineTask):
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        
        # Emit progress: task started
        if self.progress_tracker:
            await self.progress_tracker.update_task(task.name, "running", {"status": "processing"})
        
        try:
            logger.debug(f"Starting task '{task.name}'")
            
            # Get current pipeline context
            context = self._get_context()
            
            # Call function with context
            if task.is_async:
                result = await asyncio.wait_for(
                    task.func(context),
                    timeout=task.timeout
                )
            else:
                result = await asyncio.wait_for(
                    self.loop.run_in_executor(
                        self.executor,
                        task.func,
                        context
                    ),
                    timeout=task.timeout
                )
            
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.end_time = time.time()
            
            # Emit progress: task completed
            if self.progress_tracker:
                await self.progress_tracker.update_task(
                    task.name, "completed", 
                    {"duration_seconds": task.execution_time, "result_summary": str(result)[:100]}
                )
            
            logger.info(
                f"Task '{task.name}' completed in {task.execution_time:.2f}s"
            )
            
        except asyncio.TimeoutError:
            task.error = TimeoutError(f"Task {task.name} timed out after {task.timeout}s")
            task.status = TaskStatus.FAILED
            if self.progress_tracker:
                await self.progress_tracker.update_task(task.name, "failed", {"error": "Timeout"})
            logger.error(f"Task '{task.name}' timed out")
        except Exception as e:
            task.error = e
            task.status = TaskStatus.FAILED
            if self.progress_tracker:
                await self.progress_tracker.update_task(task.name, "failed", {"error": str(e)})
            logger.error(f"Task '{task.name}' failed: {str(e)}")
    
    async def execute(self) -> Dict[str, Any]:
        """
        Execute the entire pipeline in parallel
        
        Returns results from all tasks
        """
        logger.info("Starting pipeline execution")
        start_time = time.time()
        
        # Emit: Starting
        if self.progress_tracker:
            await self.progress_tracker.update_stage("Starting", "Initializing valuation pipeline", 5)
        
        wave_count = 0
        total_tasks = len(self.tasks)
        
        while True:
            # Get tasks that are ready to run
            ready_tasks = self._get_ready_tasks()
            
            if not ready_tasks:
                # Check if we're done
                incomplete = [
                    t for t in self.tasks.values()
                    if t.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED]
                ]
                if not incomplete:
                    break
                    
                # If there are incomplete tasks but none are ready, we have a cycle
                logger.error("Pipeline has cyclic dependencies or unmet dependencies")
                break
            
            wave_count += 1
            completed_tasks = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
            progress_pct = int((completed_tasks / total_tasks) * 80) + 10  # 10-90%
            
            # Run all ready tasks in parallel
            logger.debug(f"Executing {len(ready_tasks)} tasks in parallel: {ready_tasks}")
            
            if self.progress_tracker:
                await self.progress_tracker.update_stage(
                    "Processing",
                    f"Wave {wave_count}: Running {len(ready_tasks)} tasks in parallel",
                    progress_pct
                )
            
            tasks = [
                self._run_task(self.tasks[name])
                for name in ready_tasks
            ]
            
            await asyncio.gather(*tasks)
        
        # Emit: Finalizing
        if self.progress_tracker:
            await self.progress_tracker.update_stage("Finalizing", "Aggregating results", 90)
        
        total_time = time.time() - start_time
        
        # Prepare results
        results = {
            "tasks": {
                name: {
                    "status": task.status.value,
                    "result": task.result,
                    "error": str(task.error) if task.error else None,
                    "execution_time": task.execution_time
                }
                for name, task in self.tasks.items()
            },
            "total_execution_time": total_time,
            "pipeline_efficiency": self._calculate_efficiency(total_time)
        }
        
        logger.info(
            f"Pipeline completed in {total_time:.2f}s "
            f"(efficiency: {results['pipeline_efficiency']*100:.1f}%)"
        )
        
        # Emit: Complete
        if self.progress_tracker:
            await self.progress_tracker.complete(results)
        
        return results
    
    def _calculate_efficiency(self, total_time: float) -> float:
        """
        Calculate pipeline efficiency
        (actual parallelism / theoretical max)
        """
        completed_time = sum(
            task.execution_time or 0
            for task in self.tasks.values()
            if task.status == TaskStatus.COMPLETED
        )
        
        if completed_time == 0:
            return 0.0
        
        return min(1.0, (completed_time / total_time) / len(self.tasks))
    
    def reset(self):
        """Reset pipeline for reuse"""
        for task in self.tasks.values():
            task.status = TaskStatus.PENDING
            task.result = None
            task.error = None
            task.start_time = None
            task.end_time = None
        logger.info("Pipeline reset")

# ============================================================================
# Task Functions - These are the actual work units
# ============================================================================

async def geo_enrichment_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 1: Geocode address, fetch coordinates
    Independent - can start immediately
    """
    from geopy.geocoders import Nominatim
    
    logger.info("Geo enrichment: Starting address resolution")
    
    address = context.get("address", "")
    
    # Mock implementation - would use actual geocoder
    return {
        "latitude": 19.1136,
        "longitude": 72.8697,
        "geocoded_address": address,
        "confidence": 0.95
    }

async def circle_rate_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 2: Fetch government circle rate
    Independent - can start immediately
    """
    logger.info("Circle rate lookup: Starting")
    
    pincode = context.get("pincode", "")
    property_type = context.get("property_type", "apartment")
    
    # Mock implementation - would query database
    return {
        "circle_rate": 45000,  # ₹/sqft
        "pincode": pincode,
        "source": "IGRS",
        "as_of_date": "2024-04-29"
    }

async def ipi_compute_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3: Compute Infrastructure Proximity Index
    Depends on: geo_enrichment
    """
    logger.info("IPI computation: Starting")
    
    geo = context.get("geo_enrichment", {})
    lat, lon = geo.get("latitude"), geo.get("longitude")
    
    # Mock implementation - would query IPI cache
    return {
        "ipi_score": 72,
        "metro_distance_m": 2400,
        "commercial_hub_distance_m": 800,
        "school_distance_m": 600
    }

async def market_signals_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 4: Get market signals from listing data
    Independent - can start immediately
    """
    logger.info("Market signals: Starting")
    
    # Mock implementation - would query listing stats
    return {
        "median_price_per_sqft": 48000,
        "listing_density": 0.85,
        "demand_proxy": 0.72,
        "supply_months": 8.5
    }

async def vision_analysis_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 5: Run Qwen2-VL on property images
    Depends on: images provided (optional)
    """
    logger.info("Vision analysis: Starting")
    
    has_images = context.get("has_images", False)
    
    if not has_images:
        logger.info("Vision analysis: Skipping (no images provided)")
        return {
            "has_images": False,
            "condition_score": None,
            "defects": [],
            "materials": []
        }
    
    # Mock implementation - would call Ollama + Qwen2-VL
    return {
        "has_images": True,
        "condition_score": 7,
        "defects": ["minor_cracks"],
        "materials": ["marble_cladding"],
        "listing_photo_detected": False
    }

async def fraud_detection_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 6: Run 5-layer fraud detection
    Depends on: vision_analysis, circle_rate
    """
    logger.info("Fraud detection: Starting")
    
    # Mock implementation - would run all 5 fraud layers
    return {
        "phash_flag": False,
        "clip_similarity": 0.15,
        "listing_photo_detected": False,
        "size_sanity_pass": True,
        "location_consistency": 0.92,
        "risk_level": "low",
        "flags": []
    }

async def xgboost_multiplier_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 7: Get market multiplier from XGBoost
    Depends on: market_signals, ipi_compute
    """
    logger.info("XGBoost valuation: Starting")
    
    # Mock implementation - would load and run XGBoost model
    return {
        "market_multiplier": 1.18,
        "multiplier_confidence": 0.89,
        "xgb_features_used": 10
    }

async def narrative_generation_task(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 8: Generate LLM narrative explanation
    Depends on: ALL other tasks (final step)
    """
    logger.info("Narrative generation: Starting")
    
    # Mock implementation - would call Ollama + Llama 3.1
    return {
        "executive_summary": "Strong valuation with good liquidity prospects.",
        "key_drivers": ["location_premium", "building_age", "market_demand"],
        "risk_factors": [],
        "recommendation": "APPROVE"
    }
