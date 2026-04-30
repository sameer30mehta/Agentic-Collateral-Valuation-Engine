/**
 * PropScore API Client
 * 
 * Handles all communication with the backend valuation engine.
 * No hardcoded data - everything comes from the real backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export class PropScoreAPI {
  /**
   * Health check - verify backend is running
   */
  static async checkHealth() {
    try {
      const response = await fetch(`${API_BASE_URL}/health`, {
        method: 'GET',
      });
      
      if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
      
      return await response.json();
    } catch (error) {
      console.error('Backend health check failed:', error);
      throw error;
    }
  }

  /**
   * Main valuation endpoint
   * 
   * Input: Property details + optional images
   * Output: Full valuation with fraud flags + confidence scores
   * 
   * This runs the entire parallel inference pipeline.
   */
  static async runValuation(propertyData, onProgress) {
    try {
      // Validate input
      if (!propertyData.address || !propertyData.carpet_area || !propertyData.pincode) {
        throw new Error('Missing required property fields');
      }

      // Report: Starting valuation
      if (onProgress) {
        onProgress({
          stage: 'initializing',
          message: 'Preparing valuation...',
          progress: 5
        });
      }

      // Build request payload
      const payload = {
        address: propertyData.address,
        latitude: propertyData.latitude,
        longitude: propertyData.longitude,
        property_type: propertyData.property_type || 'apartment',
        config: propertyData.config,
        carpet_area: propertyData.carpet_area,
        age_bucket: propertyData.age_bucket,
        occupancy_status: propertyData.occupancy_status,
        legal_status: propertyData.legal_status,
        pincode: propertyData.pincode,
        city: propertyData.city,
        images: propertyData.images || []
      };

      // Report: Sending to backend
      if (onProgress) {
        onProgress({
          stage: 'dispatching_agents',
          message: 'Sending to backend agents...',
          progress: 10
        });
      }

      const response = await fetch(`${API_BASE_URL}/valuate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `Valuation failed: ${response.status}`);
      }

      const result = await response.json();

      // Report: Valuation complete
      if (onProgress) {
        onProgress({
          stage: 'complete',
          message: 'Valuation complete',
          progress: 100,
          result: result
        });
      }

      return result;

    } catch (error) {
      console.error('Valuation error:', error);
      throw error;
    }
  }

  /**
   * Real-time pipeline progress monitoring (WebSocket)
   * 
   * In production: connects to WebSocket endpoint for live progress
   * Shows each stage: geo enrichment, VLM analysis, fraud detection, etc
   */
  static subscribeToProgress(valuationId, onUpdate) {
    // WebSocket endpoint: ws://localhost:8000/progress/{valuationId}
    // For now: HTTP polling fallback
    
    const pollInterval = setInterval(async () => {
      try {
        // Would query GET /valuate/{valuationId}/status
        // onUpdate({ stage: 'vision_analysis', progress: 45 });
      } catch (error) {
        console.error('Progress polling error:', error);
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }

  /**
   * Validate address via geocoding
   */
  static async validateAddress(address, city) {
    try {
      const response = await fetch(`${API_BASE_URL}/geocode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, city })
      });

      if (!response.ok) throw new Error('Address validation failed');
      
      return await response.json();
    } catch (error) {
      console.error('Address validation error:', error);
      throw error;
    }
  }

  /**
   * Get market comparables for a property
   */
  static async getComparables(pincode, config, carpetArea) {
    try {
      const response = await fetch(
        `${API_BASE_URL}/comparables?pincode=${pincode}&config=${config}&area=${carpetArea}`,
        { method: 'GET' }
      );

      if (!response.ok) throw new Error('Failed to fetch comparables');
      
      return await response.json();
    } catch (error) {
      console.error('Comparables fetch error:', error);
      throw error;
    }
  }

  /**
   * Batch valuation (for multiple properties)
   */
  static async batchValuate(propertyList) {
    try {
      const response = await fetch(`${API_BASE_URL}/batch-valuate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ properties: propertyList })
      });

      if (!response.ok) throw new Error('Batch valuation failed');
      
      return await response.json();
    } catch (error) {
      console.error('Batch valuation error:', error);
      throw error;
    }
  }

  /**
   * Export report (PDF generation)
   */
  static async generateReport(valuationId, format = 'pdf') {
    try {
      const response = await fetch(
        `${API_BASE_URL}/report/${valuationId}?format=${format}`,
        { method: 'GET' }
      );

      if (!response.ok) throw new Error('Report generation failed');

      if (format === 'pdf') {
        return await response.blob();
      } else {
        return await response.json();
      }
    } catch (error) {
      console.error('Report generation error:', error);
      throw error;
    }
  }
}

export default PropScoreAPI;
