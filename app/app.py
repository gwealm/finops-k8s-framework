import logging
from fastapi import FastAPI, HTTPException
import uvicorn
from typing import List
from datetime import datetime
from prometheus_fastapi_instrumentator import Instrumentator
from modules.metrics import finops_http_requests_total

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the FastAPI app
app = FastAPI(title="FinOps API", description="A FinOps API for Kubernetes cost optimization")

# Initialize and apply instrumentation BEFORE defining routes
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
    inprogress_name="finops_api_inprogress",
    inprogress_labels=True,
)
instrumentator.instrument(app).expose(app)
logger.info("Application instrumented with Prometheus metrics at /metrics")

# Import our modules (AFTER instrumenting the app)
from modules.models import CostEfficiency, Recommendation, CostAnomaly, CostForecast
from modules.insights import (
    get_namespace_resources, 
    calculate_cost_efficiency,
    generate_recommendations,
    detect_cost_anomalies,
    generate_cost_forecast
)

# Now define all your routes and other app functionality
# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# API version
@app.get("/version")
def version():
    """Return API version information"""
    return {"version": "0.2.0", "api": "FinOps K8s Cost Optimization"}

# Error handling wrapper for insights functions
def handle_errors(func, *args, **kwargs):
    """Wrapper to catch and log errors in insight functions"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error in {func.__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

# Endpoint to get cost efficiency by namespace
@app.get("/cost-efficiency", response_model=List[CostEfficiency])
def get_cost_efficiency():
    """Get cost efficiency scores for all namespaces"""
    resource_data = handle_errors(get_namespace_resources)
    return [handle_errors(calculate_cost_efficiency, data) for data in resource_data]

# Endpoint to get optimization recommendations
@app.get("/recommendations", response_model=List[Recommendation])
def get_recommendations():
    """Get cost optimization recommendations for all namespaces"""
    resource_data = handle_errors(get_namespace_resources)
    all_recommendations = []
    
    for data in resource_data:
        namespace_recommendations = handle_errors(generate_recommendations, data)
        all_recommendations.extend(namespace_recommendations)
    
    return all_recommendations

# Endpoint to get cost anomalies
@app.get("/cost-anomalies", response_model=List[CostAnomaly])
def get_cost_anomalies():
    """Get cost anomaly detection results for all namespaces"""
    resource_data = handle_errors(get_namespace_resources)
    return [handle_errors(detect_cost_anomalies, data.namespace) for data in resource_data]

# Endpoint to get cost forecasts
@app.get("/cost-forecasts", response_model=List[CostForecast])
def get_cost_forecasts():
    """Get 30-day cost forecasts for all namespaces"""
    resource_data = handle_errors(get_namespace_resources)
    return [handle_errors(generate_cost_forecast, data.namespace) for data in resource_data]

# Endpoint to get all insights in one call
@app.get("/all-insights")
def get_all_insights():
    """Get all cost insights in one API call"""
    resource_data = handle_errors(get_namespace_resources)
    
    # Generate all insights
    efficiencies = [handle_errors(calculate_cost_efficiency, data) for data in resource_data]
    
    recommendations = []
    for data in resource_data:
        namespace_recommendations = handle_errors(generate_recommendations, data)
        recommendations.extend(namespace_recommendations)
    
    anomalies = [handle_errors(detect_cost_anomalies, data.namespace) for data in resource_data]
    forecasts = [handle_errors(generate_cost_forecast, data.namespace) for data in resource_data]
    
    return {
        "cost_efficiencies": efficiencies,
        "recommendations": recommendations,
        "cost_anomalies": anomalies, 
        "cost_forecasts": forecasts
    }

# Force update of app metrics
@app.post("/update-metrics")
def force_update_metrics():
    """Force a Prometheus metrics update"""
    # This endpoint is here just for backward compatibility
    # The metrics are updated automatically with each request
    return {"status": "Metrics are updated automatically with each request"}

@app.middleware("http")
async def metrics_middleware(request, call_next):
    response = await call_next(request)
    
    # Update request metrics
    finops_http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    return response

@app.on_event("startup")
async def startup():
    # Initialize metrics by running insight functions
    try:
        logger.info("Initializing metrics...")
        resource_data = handle_errors(get_namespace_resources)
        
        if resource_data:
            for data in resource_data:
                # Call each function to generate initial metrics
                handle_errors(calculate_cost_efficiency, data)
                handle_errors(generate_recommendations, data)
                handle_errors(detect_cost_anomalies, data.namespace)
                handle_errors(generate_cost_forecast, data.namespace)
                
            logger.info(f"Metrics initialized for {len(resource_data)} namespaces")
    except Exception as e:
        logger.error(f"Error initializing metrics: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, log_level="info")
