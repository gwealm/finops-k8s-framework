from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union


class ResourceData(BaseModel):
    """Resource usage and allocation data for a namespace"""
    namespace: str
    cpu_usage: float
    cpu_request: float
    cpu_limit: float
    memory_usage: float
    memory_request: float
    memory_limit: float
    cost: float


class CostAnomaly(BaseModel):
    """Cost anomaly detection result"""
    namespace: str
    usual_cost: float
    current_cost: float
    increase_percent: float
    anomaly_score: float


class Recommendation(BaseModel):
    """Cost optimization recommendation"""
    namespace: str
    recommendation_type: str
    description: str
    estimated_savings: float
    current_value: Union[float, str]
    recommended_value: Union[float, str]


class CostEfficiency(BaseModel):
    """Cost efficiency metrics"""
    namespace: str
    efficiency_score: float
    wasted_cpu_percent: float
    wasted_memory_percent: float