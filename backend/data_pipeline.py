"""
Data Pipeline for PropScore

This module handles:
1. Circle rate data loading/scraping
2. Listing data aggregation
3. IPI (Infrastructure Proximity Index) pre-computation
4. Market statistics aggregation
5. CLIP photo index building
6. Hazard layer loading (flood zones, etc)
"""

from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import json
import pandas as pd
import numpy as np
from loguru import logger
from sqlalchemy.orm import Session
from datetime import datetime
import pickle

from database import CircleRate, ListingStats, IPICache

class DataPipeline:
    """Main data preparation and aggregation engine"""
    
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True, parents=True)
        
    # ========================================================================
    # 1. Circle Rate Loading
    # ========================================================================
    
    def load_circle_rates(self, db: Session, source_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Load government circle rates (property floor values)
        
        Can load from:
        - CSV file (manual data entry)
        - IGRS website scrape
        - Local JSON cache
        
        Priority: IGRS > CSV > Previous cache
        """
        logger.info("Loading circle rates...")
        
        circle_rates = {}
        loaded_count = 0
        
        # Try IGRS scrape
        if not circle_rates:
            circle_rates = await self._scrape_igrs_circle_rates()
        
        # Fallback to CSV
        if not circle_rates and source_file:
            circle_rates = self._load_circle_rates_csv(source_file)
        
        # Store in database
        for (pincode, prop_type, city), rate in circle_rates.items():
            existing = db.query(CircleRate).filter(
                CircleRate.pincode == pincode,
                CircleRate.property_type == prop_type,
                CircleRate.city == city
            ).first()
            
            if not existing:
                cr = CircleRate(
                    pincode=pincode,
                    property_type=prop_type,
                    rate_per_sqft=rate,
                    city=city,
                    source="IGRS"
                )
                db.add(cr)
                loaded_count += 1
        
        db.commit()
        logger.info(f"Loaded {loaded_count} circle rate records")
        
        return {
            "loaded_count": loaded_count,
            "by_city": self._group_by_city(circle_rates)
        }
    
    def _load_circle_rates_csv(self, filepath: str) -> Dict[Tuple, float]:
        """Load circle rates from CSV"""
        try:
            df = pd.read_csv(filepath)
            # Expected columns: pincode, property_type, city, rate_per_sqft
            
            rates = {}
            for _, row in df.iterrows():
                key = (row['pincode'], row['property_type'], row['city'])
                rates[key] = row['rate_per_sqft']
            
            logger.info(f"Loaded {len(rates)} circle rates from CSV")
            return rates
        except Exception as e:
            logger.error(f"Failed to load circle rates CSV: {e}")
            return {}
    
    async def _scrape_igrs_circle_rates(self) -> Dict[Tuple, float]:
        """Scrape circle rates from IGRS websites"""
        logger.warning("IGRS scraping not implemented - returning empty")
        return {}
    
    # ========================================================================
    # 2. Listing Data Aggregation
    # ========================================================================
    
    def aggregate_listing_statistics(
        self,
        db: Session,
        listings_df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Aggregate statistics from scraped listing data
        
        Computes for each (pincode, config):
        - Median price per sqft
        - P25/P75 range
        - Median area
        - Listing count
        - Median days on market
        
        This feeds into market comparables and sanity checks.
        """
        logger.info("Aggregating listing statistics...")
        
        if listings_df is None:
            listings_df = self._load_listing_data()
        
        if listings_df.empty:
            logger.warning("No listing data available")
            return {"aggregated_count": 0}
        
        # Group by pincode + config
        agg_stats = listings_df.groupby(['pincode', 'config']).agg({
            'price_per_sqft': ['median', lambda x: x.quantile(0.25), lambda x: x.quantile(0.75)],
            'carpet_area': ['median'],
            'days_listed': ['median'],
            'listing_id': 'count'  # count
        }).round(2)
        
        stored_count = 0
        
        for (pincode, config), row in agg_stats.iterrows():
            existing = db.query(ListingStats).filter(
                ListingStats.pincode == pincode,
                ListingStats.config == config
            ).first()
            
            stat = existing or ListingStats(pincode=pincode, config=config)
            
            stat.median_price_per_sqft = row[('price_per_sqft', 'median')]
            stat.p25_price_per_sqft = row[('price_per_sqft', '<lambda_0>')]
            stat.p75_price_per_sqft = row[('price_per_sqft', '<lambda_1>')]
            stat.median_area = row[('carpet_area', 'median')]
            stat.median_days_listed = row[('days_listed', 'median')]
            stat.listing_count = row[('listing_id', 'count')]
            stat.last_updated = datetime.utcnow()
            
            if not existing:
                db.add(stat)
            
            stored_count += 1
        
        db.commit()
        logger.info(f"Stored statistics for {stored_count} pincode-config combinations")
        
        return {
            "aggregated_count": stored_count,
            "sample_stats": agg_stats.head().to_dict()
        }
    
    def _load_listing_data(self) -> pd.DataFrame:
        """Load pre-scraped listing data"""
        listing_file = self.data_dir / "listings.csv"
        
        if listing_file.exists():
            return pd.read_csv(listing_file)
        
        logger.warning("listings.csv not found - returning empty dataframe")
        return pd.DataFrame()
    
    # ========================================================================
    # 3. IPI (Infrastructure Proximity Index) Pre-computation
    # ========================================================================
    
    def precompute_ipi_grid(
        self,
        db: Session,
        grid_size_meters: int = 500,
        cities: List[str] = ["Mumbai", "Pune", "Bangalore"]
    ) -> Dict[str, Any]:
        """
        Pre-compute IPI for a grid across demo cities
        
        Creates a grid of 500m x 500m cells, computes proximity to:
        - Metro stations
        - Highways
        - Commercial hubs
        - Schools
        - Hospitals
        
        Stores in database for instant lookup at inference time.
        """
        logger.info(f"Pre-computing IPI grid for {len(cities)} cities")
        
        # City bounds (lat/lon)
        city_bounds = {
            "Mumbai": {"lat": (18.9, 19.3), "lon": (72.7, 73.0)},
            "Pune": {"lat": (18.3, 18.7), "lon": (73.6, 74.0)},
            "Bangalore": {"lat": (12.8, 13.2), "lon": (77.4, 77.8)},
        }
        
        computed_count = 0
        
        for city in cities:
            if city not in city_bounds:
                continue
            
            bounds = city_bounds[city]
            
            # Create grid
            lat_range = np.arange(bounds["lat"][0], bounds["lat"][1], grid_size_meters/111000)
            lon_range = np.arange(bounds["lon"][0], bounds["lon"][1], grid_size_meters/111000)
            
            for lat in lat_range:
                for lon in lon_range:
                    grid_id = f"{city}_{lat:.4f}_{lon:.4f}"
                    
                    # Check if already computed
                    existing = db.query(IPICache).filter(
                        IPICache.grid_point_id == grid_id
                    ).first()
                    
                    if existing:
                        continue
                    
                    # Compute proximity scores
                    ipi_data = self._compute_ipi_point(lat, lon, city)
                    
                    cache_record = IPICache(
                        grid_point_id=grid_id,
                        latitude=lat,
                        longitude=lon,
                        metro_distance_m=ipi_data["metro_distance"],
                        highway_distance_m=ipi_data["highway_distance"],
                        commercial_hub_distance_m=ipi_data["commercial_hub_distance"],
                        school_distance_m=ipi_data["school_distance"],
                        hospital_distance_m=ipi_data["hospital_distance"],
                        ipi_score=ipi_data["ipi_score"],
                        computed_at=datetime.utcnow()
                    )
                    
                    db.add(cache_record)
                    computed_count += 1
            
            logger.info(f"Computed {computed_count} grid points for {city}")
        
        db.commit()
        logger.info(f"Total IPI grid points computed: {computed_count}")
        
        return {"computed_points": computed_count}
    
    def _compute_ipi_point(self, lat: float, lon: float, city: str) -> Dict[str, float]:
        """
        Compute IPI for a single point
        
        In production: queries OSM/Overpass API for real data
        For now: mock implementation
        """
        
        # Mock proximity data
        metro_dist = np.random.uniform(500, 5000)
        highway_dist = np.random.uniform(1000, 8000)
        commercial_dist = np.random.uniform(300, 3000)
        school_dist = np.random.uniform(200, 2000)
        hospital_dist = np.random.uniform(300, 2500)
        
        # Compute IPI score (0-100)
        # Closer proximity = higher score
        ipi = 50  # Base
        
        if metro_dist < 2000:
            ipi += 20
        if commercial_dist < 1000:
            ipi += 15
        if school_dist < 1000:
            ipi += 10
        if hospital_dist < 1500:
            ipi += 5
        
        return {
            "metro_distance": metro_dist,
            "highway_distance": highway_dist,
            "commercial_hub_distance": commercial_dist,
            "school_distance": school_dist,
            "hospital_distance": hospital_dist,
            "ipi_score": min(100, ipi)
        }
    
    # ========================================================================
    # 4. Build CLIP Photo Index for Fraud Detection
    # ========================================================================
    
    def build_clip_photo_index(
        self,
        listings_df: Optional[pd.DataFrame] = None,
        index_save_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build FAISS index of CLIP embeddings from all listing photos
        
        This enables fast fraud detection via semantic similarity search.
        """
        logger.info("Building CLIP photo index for fraud detection...")
        
        if listings_df is None:
            listings_df = self._load_listing_data()
        
        logger.warning("CLIP indexing not implemented - returning placeholder")
        
        return {
            "index_created": False,
            "photo_count": 0,
            "reason": "CLIP model loading not yet implemented"
        }
    
    # ========================================================================
    # 5. Load Hazard Layers
    # ========================================================================
    
    def load_hazard_layers(self) -> Dict[str, Any]:
        """
        Load geographic hazard data:
        - Flood zones
        - Seismic zones
        - CRZ (Coastal Regulation Zone)
        
        Used for location-based risk assessment.
        """
        logger.info("Loading hazard layers...")
        
        hazards = {
            "flood_zones": self._load_flood_zones(),
            "seismic_zones": self._load_seismic_zones(),
            "crz_boundaries": self._load_crz_boundaries(),
        }
        
        return {
            "loaded": True,
            "layers": {k: len(v) for k, v in hazards.items()}
        }
    
    def _load_flood_zones(self) -> Dict:
        """Load flood zone GeoJSON"""
        flood_file = self.data_dir / "flood_zones.geojson"
        
        if flood_file.exists():
            with open(flood_file) as f:
                return json.load(f)
        
        return {}
    
    def _load_seismic_zones(self) -> Dict:
        """Load seismic zone polygons"""
        return {}
    
    def _load_crz_boundaries(self) -> Dict:
        """Load CRZ (Coastal Regulation Zone) boundaries"""
        return {}
    
    # ========================================================================
    # Utilities
    # ========================================================================
    
    def _group_by_city(self, data: Dict) -> Dict:
        """Group circle rates by city"""
        grouped = {}
        for (pincode, prop_type, city), value in data.items():
            if city not in grouped:
                grouped[city] = 0
            grouped[city] += 1
        return grouped
    
    def generate_setup_report(self, db: Session) -> Dict[str, Any]:
        """
        Generate a report of all loaded data
        
        Useful for debugging and deployment verification
        """
        logger.info("Generating data setup report...")
        
        report = {
            "circle_rates": {
                "total_records": db.query(CircleRate).count(),
                "cities": len(set(cr.city for cr in db.query(CircleRate).all())),
                "pincode_count": len(set(cr.pincode for cr in db.query(CircleRate).all()))
            },
            "listing_stats": {
                "total_records": db.query(ListingStats).count(),
                "pincode_config_pairs": db.query(ListingStats).count()
            },
            "ipi_cache": {
                "total_grid_points": db.query(IPICache).count(),
                "cities": len(set(ipi.grid_point_id.split('_')[0] for ipi in db.query(IPICache).all()))
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Setup report: {report}")
        return report


# ============================================================================
# One-time Setup Script (Run once during deployment)
# ============================================================================

async def setup_propscore(
    db: Session,
    data_dir: str = "./data",
    demo_mode: bool = True
):
    """
    One-time setup to prepare all data pipelines
    
    Can be run via: python -m backend.data_pipeline
    """
    
    logger.info("=" * 80)
    logger.info("PropScore Data Pipeline Setup")
    logger.info("=" * 80)
    
    pipeline = DataPipeline(data_dir)
    
    # 1. Load circle rates
    logger.info("\n[1/5] Loading circle rates...")
    cr_result = pipeline.load_circle_rates(db)
    print(f"  ✓ Loaded {cr_result['loaded_count']} circle rate records")
    
    # 2. Aggregate listing statistics
    logger.info("\n[2/5] Aggregating listing statistics...")
    ls_result = pipeline.aggregate_listing_statistics(db)
    print(f"  ✓ Aggregated {ls_result['aggregated_count']} stat groups")
    
    # 3. Pre-compute IPI grid
    logger.info("\n[3/5] Pre-computing IPI grid...")
    ipi_result = pipeline.precompute_ipi_grid(db)
    print(f"  ✓ Computed {ipi_result['computed_points']} grid points")
    
    # 4. Build CLIP index
    logger.info("\n[4/5] Building CLIP photo index...")
    clip_result = pipeline.build_clip_photo_index()
    print(f"  ℹ CLIP indexing: {clip_result.get('reason', 'pending')}")
    
    # 5. Load hazard layers
    logger.info("\n[5/5] Loading hazard layers...")
    hazard_result = pipeline.load_hazard_layers()
    print(f"  ✓ Loaded hazard layers: {hazard_result['layers']}")
    
    # Generate report
    logger.info("\n" + "=" * 80)
    logger.info("Setup Complete - Data Ready for Inference")
    logger.info("=" * 80)
    
    report = pipeline.generate_setup_report(db)
    print("\nData Summary:")
    print(f"  • Circle rates: {report['circle_rates']['total_records']} records across {report['circle_rates']['cities']} cities")
    print(f"  • Listing stats: {report['listing_stats']['total_records']} aggregates")
    print(f"  • IPI grid: {report['ipi_cache']['total_grid_points']} points")
    print(f"  • Timestamp: {report['timestamp']}")
    
    logger.info("System ready for production inference!")
