import requests
from fastapi import FastAPI, Query, HTTPException, Depends
from typing import Optional, List, Dict, Any
import logging
import uvicorn
from datetime import datetime, timedelta
from pydantic import BaseModel
import os
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FinOps API", description="A simple FinOps API for Kubernetes cost optimization")

# Environment variables with default values
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
OPENCOST_URL = os.getenv("OPENCOST_URL", "http://opencost.opencost.svc.cluster.local:9003")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://prometheus-grafana.monitoring.svc.cluster.local:3000")
CPU_HOURLY_COST = float(os.getenv("CPU_HOURLY_COST", "0.04"))
MEMORY_GB_HOURLY_COST = float(os.getenv("MEMORY_GB_HOURLY_COST", "0.01"))


# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# API version
@app.get("/version")
def version():
    return {"version": "0.1.0", "api": "FinOps K8s Cost Optimization"}
