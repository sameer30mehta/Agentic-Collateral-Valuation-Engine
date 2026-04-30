"""
5-Layer Fraud Detection System for PropScore

Layer 1: pHash (perceptual hashing) - duplicate images
Layer 2: CLIP semantic similarity - similar photos
Layer 3: VLM listing photo detector - staged/professional photos
Layer 4: Size sanity check - area vs market norms
Layer 5: Location consistency - scene geography validation
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from loguru import logger
import numpy as np
from PIL import Image
import imagehash
import requests
import io

@dataclass
class FraudFlag:
    layer: int
    flag_name: str
    severity: str  # low, medium, high, critical
    description: str
    evidence: Dict[str, Any]
    confidence: float

class FraudDetectionEngine:
    """Main fraud detection engine"""
    
    def __init__(self, listing_photo_index_path: Optional[str] = None):
        self.listing_photo_index_path = listing_photo_index_path
        self.phash_database = {}  # In production: load from cache
        self.clip_index = None  # In production: load FAISS index
        self.flags: List[FraudFlag] = []
        
    async def analyze(
        self,
        property_images: List[Dict],
        circle_rate: float,
        carpet_area: float,
        pincode: str,
        claimed_type: str,
        listing_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Run all 5 fraud layers"""
        
        self.flags = []
        results = {
            "layer_1_phash": None,
            "layer_2_clip": None,
            "layer_3_vlm_detector": None,
            "layer_4_size_sanity": None,
            "layer_5_location": None,
        }
        
        logger.info(f"Starting fraud detection for property in {pincode}")
        
        # Layer 1: pHash (CPU, fast)
        if property_images:
            results["layer_1_phash"] = await self._layer_1_phash(property_images)
        
        # Layer 2: CLIP similarity (GPU, semantic)
        if property_images and self.clip_index:
            results["layer_2_clip"] = await self._layer_2_clip(property_images)
        
        # Layer 3: VLM listing photo detector
        if property_images:
            results["layer_3_vlm_detector"] = await self._layer_3_vlm_detector(property_images)
        
        # Layer 4: Size sanity check (instant)
        results["layer_4_size_sanity"] = await self._layer_4_size_sanity(
            carpet_area, pincode, claimed_type, listing_data
        )
        
        # Layer 5: Location consistency (CLIP zero-shot)
        if property_images:
            results["layer_5_location"] = await self._layer_5_location(property_images)
        
        # Aggregate risk level
        risk_level = self._calculate_risk_level()
        
        return {
            "layers": results,
            "flags": [
                {
                    "layer": f.layer,
                    "flag": f.flag_name,
                    "severity": f.severity,
                    "description": f.description,
                    "evidence": f.evidence,
                    "confidence": f.confidence
                }
                for f in self.flags
            ],
            "risk_level": risk_level,
            "recommendation": self._get_recommendation()
        }
    
    # ========================================================================
    # Layer 1: pHash (Perceptual Hashing)
    # ========================================================================
    
    async def _layer_1_phash(self, images: List[Dict]) -> Dict[str, Any]:
        """
        Detect near-duplicate images using perceptual hashing
        
        Detects: same photo used in multiple applications/listings
        Speed: <10ms per image
        """
        logger.info("Layer 1: Running pHash analysis")
        
        result = {
            "duplicates_found": False,
            "matches": [],
            "hashes": []
        }
        
        for img in images:
            try:
                # Download image
                response = requests.get(img["url"], timeout=5)
                pil_image = Image.open(io.BytesIO(response.content))
                
                # Generate pHash
                hash_value = str(imagehash.phash(pil_image))
                result["hashes"].append(hash_value)
                
                # Check against database
                if hash_value in self.phash_database:
                    match = self.phash_database[hash_value]
                    result["duplicates_found"] = True
                    result["matches"].append({
                        "matched_listing_id": match["listing_id"],
                        "matched_address": match["address"],
                        "matched_date": match["date"]
                    })
                    
                    self.flags.append(FraudFlag(
                        layer=1,
                        flag_name="EXACT_PHOTO_DUPLICATE",
                        severity="critical",
                        description=f"Exact duplicate photo detected. Previously used at {match['address']}",
                        evidence={"hash": hash_value, "previous_match": match},
                        confidence=0.99
                    ))
                    
            except Exception as e:
                logger.warning(f"pHash analysis failed for image: {str(e)}")
        
        return result
    
    # ========================================================================
    # Layer 2: CLIP Semantic Similarity
    # ========================================================================
    
    async def _layer_2_clip(self, images: List[Dict]) -> Dict[str, Any]:
        """
        Semantic image similarity using CLIP
        
        Detects: same property photo from different angles/times
        Speed: ~500ms for vectorization, then instant FAISS search
        """
        logger.info("Layer 2: Running CLIP semantic similarity")
        
        if not self.clip_index:
            return {"similarity_scores": [], "high_similarity_matches": []}
        
        result = {
            "similarity_scores": [],
            "high_similarity_matches": []
        }
        
        for img in images:
            try:
                # Encode image with CLIP (mock implementation)
                # In production: use clip.encode_image()
                embedding = np.random.randn(512).astype(np.float32)
                
                # Search index
                distances, indices = self.clip_index.search(embedding.reshape(1, -1), k=5)
                
                # Process top matches
                for dist, idx in zip(distances[0], indices[0]):
                    similarity = 1 - (dist / 2)  # Normalize to 0-1
                    
                    if similarity > 0.85:
                        result["high_similarity_matches"].append({
                            "listing_id": idx,
                            "similarity": float(similarity),
                            "property": "matched_property_details"
                        })
                        
                        self.flags.append(FraudFlag(
                            layer=2,
                            flag_name="HIGH_SEMANTIC_SIMILARITY",
                            severity="high" if similarity > 0.92 else "medium",
                            description=f"Photo semantically similar to listing ID {idx} (similarity: {similarity:.2f})",
                            evidence={"similarity": similarity, "reference_listing": idx},
                            confidence=similarity
                        ))
                    
                    result["similarity_scores"].append({
                        "listing_id": idx,
                        "similarity": float(similarity)
                    })
                
            except Exception as e:
                logger.warning(f"CLIP analysis failed: {str(e)}")
        
        return result
    
    # ========================================================================
    # Layer 3: VLM Listing Photo Detector
    # ========================================================================
    
    async def _layer_3_vlm_detector(self, images: List[Dict]) -> Dict[str, Any]:
        """
        Detect professionally staged/processed photos
        
        Detects:
        - HDR processing artifacts
        - Professional staging (too clean, absent personal items)
        - Wide-angle lens distortion
        - Developer marketing photos
        
        Uses: Main Qwen2-VL pipeline
        Speed: ~3-5s per image
        """
        logger.info("Layer 3: Running VLM listing photo detector")
        
        result = {
            "listing_photos_detected": False,
            "detections": []
        }
        
        for img in images:
            try:
                # Mock detection - in production would call Qwen2-VL
                detection = {
                    "is_listing_photo": False,
                    "hdr_artifacts": 0.15,
                    "staging_score": 0.25,  # 0-1
                    "professional_processing": 0.20,
                    "lens_distortion": 0.10
                }
                
                if detection["staging_score"] > 0.60:
                    detection["is_listing_photo"] = True
                    result["listing_photos_detected"] = True
                    
                    self.flags.append(FraudFlag(
                        layer=3,
                        flag_name="LISTING_PHOTO_DETECTED",
                        severity="high",
                        description="Photo appears professionally staged/processed. Possibly from listing website.",
                        evidence={
                            "staging_score": detection["staging_score"],
                            "hdr_artifacts": detection["hdr_artifacts"],
                            "processing_indicators": detection
                        },
                        confidence=detection["staging_score"]
                    ))
                
                result["detections"].append({
                    "image_url": img["url"],
                    "analysis": detection
                })
                
            except Exception as e:
                logger.warning(f"VLM detector failed: {str(e)}")
        
        return result
    
    # ========================================================================
    # Layer 4: Size Sanity Check
    # ========================================================================
    
    async def _layer_4_size_sanity(
        self,
        carpet_area: float,
        pincode: str,
        claimed_type: str,
        listing_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Check claimed carpet area against market norms
        
        Detects: Obviously false carpet area claims
        Speed: <1ms (pure lookup + arithmetic)
        Data: Pre-aggregated market stats by pincode + config
        """
        logger.info(f"Layer 4: Running size sanity check for {carpet_area} sqft {claimed_type}")
        
        result = {
            "pass": True,
            "claimed_area": carpet_area,
            "market_range": None,
            "anomaly_score": 0.0
        }
        
        # Get market stats (in production: from DB)
        market_stats = self._get_market_stats(pincode, claimed_type)
        
        if market_stats:
            p5 = market_stats.get("p5_area", 0)
            p95 = market_stats.get("p95_area", 10000)
            median = market_stats.get("median_area", 1500)
            
            result["market_range"] = {"p5": p5, "median": median, "p95": p95}
            
            # Sanity check
            if carpet_area < p5 * 0.5:  # <50% of p5
                result["pass"] = False
                result["anomaly_score"] = 0.95
                
                self.flags.append(FraudFlag(
                    layer=4,
                    flag_name="AREA_FAR_BELOW_MARKET",
                    severity="high",
                    description=f"Claimed area ({carpet_area} sqft) is far below market norm for {claimed_type} in {pincode} (p5={p5} sqft)",
                    evidence={"claimed": carpet_area, "market_range": result["market_range"]},
                    confidence=0.90
                ))
            
            elif carpet_area > p95 * 2:  # >200% of p95
                result["pass"] = False
                result["anomaly_score"] = 0.85
                
                self.flags.append(FraudFlag(
                    layer=4,
                    flag_name="AREA_FAR_ABOVE_MARKET",
                    severity="medium",
                    description=f"Claimed area ({carpet_area} sqft) is far above market norm for {claimed_type} in {pincode} (p95={p95} sqft)",
                    evidence={"claimed": carpet_area, "market_range": result["market_range"]},
                    confidence=0.80
                ))
        
        return result
    
    # ========================================================================
    # Layer 5: Location Scene Consistency (CLIP Zero-Shot)
    # ========================================================================
    
    async def _layer_5_location(self, images: List[Dict]) -> Dict[str, Any]:
        """
        Check if photo scenes match claimed geographic region
        
        Uses CLIP's geographic understanding to classify:
        - Dense urban (Mumbai, Bangalore high-rise)
        - Suburban (Pune, Hyderabad mid-rise)
        - Semi-rural (low-density residential)
        - Coastal (visible water, architectural style)
        
        Detects: Borrower using irrelevant property photos from different region
        Speed: ~500ms per image
        """
        logger.info("Layer 5: Running location scene consistency check")
        
        result = {
            "location_consistency": 1.0,
            "scene_classifications": [],
            "inconsistency_flags": []
        }
        
        scene_descriptions = [
            "dense urban high-rise apartment complex",
            "suburban residential area",
            "semi-rural low-density houses",
            "coastal waterfront property",
            "gated community with landscaping"
        ]
        
        for img in images:
            try:
                # Mock CLIP zero-shot classification
                # In production: use CLIP's classification on scene descriptors
                scores = {desc: np.random.rand() for desc in scene_descriptions}
                top_scene = max(scores, key=scores.get)
                
                result["scene_classifications"].append({
                    "image": img["url"],
                    "top_classification": top_scene,
                    "all_scores": scores
                })
                
                # For now, just track consistency
                # In production: would validate against claimed location
                
            except Exception as e:
                logger.warning(f"Location check failed: {str(e)}")
        
        return result
    
    # ========================================================================
    # Risk Aggregation
    # ========================================================================
    
    def _calculate_risk_level(self) -> str:
        """Calculate overall risk level from all flags"""
        
        if not self.flags:
            return "low"
        
        critical_count = sum(1 for f in self.flags if f.severity == "critical")
        high_count = sum(1 for f in self.flags if f.severity == "high")
        
        if critical_count > 0:
            return "critical"
        elif high_count >= 2:
            return "high"
        elif high_count >= 1:
            return "medium"
        else:
            return "low"
    
    def _get_recommendation(self) -> str:
        """Get recommendation based on risk"""
        risk = self._calculate_risk_level()
        
        if risk == "critical":
            return "REJECT - Critical fraud signals detected. Manual review required."
        elif risk == "high":
            return "MANUAL_REVIEW - Significant fraud indicators. Request additional documentation."
        elif risk == "medium":
            return "INVESTIGATE - Some fraud signals present. May be false positives."
        else:
            return "ACCEPT - Low fraud risk. Proceed with normal workflow."
    
    def _get_market_stats(self, pincode: str, config: str) -> Optional[Dict]:
        """Fetch pre-aggregated market statistics"""
        # In production: query from database
        
        mock_stats = {
            ("400051", "2BHK"): {
                "median_area": 1100,
                "p5_area": 750,
                "p95_area": 1600,
                "sample_size": 145
            },
            ("400051", "3BHK"): {
                "median_area": 1800,
                "p5_area": 1200,
                "p95_area": 2500,
                "sample_size": 203
            },
        }
        
        return mock_stats.get((pincode, config))
