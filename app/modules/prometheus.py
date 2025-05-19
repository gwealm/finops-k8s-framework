import logging
import os
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from prometheus_api_client import PrometheusConnect, PrometheusApiClientException
import requests

logger = logging.getLogger(__name__)

# Environment variables with default values
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://prometheus-pushgateway.monitoring.svc.cluster.local:9091")

# Global Prometheus client
prom_client = None

def get_prometheus_client():
    """
    Get or initialize the Prometheus client
    """
    global prom_client
    if prom_client is None:
        try:
            prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
            prom_client = PrometheusConnect(url=prometheus_url, disable_ssl=True, headers={"Connection": "close"})
            prom_client.check_prometheus_connection()
            logger.info(f"Successfully connected to Prometheus at {prometheus_url}")
        except Exception as e:
            logger.error(f"Failed to initialize Prometheus client: {e}")
            prom_client = FallbackPrometheusClient(PROMETHEUS_URL)
    return prom_client

class FallbackPrometheusClient:
    """
    Fallback implementation if the PrometheusConnect client fails to initialize
    """
    def __init__(self, url):
        self.url = url
        logger.info(f"Using fallback Prometheus client for {url}")
    
    def custom_query(self, query):
        """
        Fallback implementation of the custom_query method
        """
        try:
            response = requests.get(f"{self.url}/api/v1/query", params={"query": query})
            response.raise_for_status()
            data = response.json()
            if 'data' in data and 'result' in data['data']:
                return data['data']['result']
            return []
        except Exception as e:
            logger.error(f"Error in fallback Prometheus query: {e}")
            return []

def query_prometheus(query: str) -> Dict[str, Any]:
    """
    Execute a PromQL query against the Prometheus API using the client library
    """
    try:
        client = get_prometheus_client()
        result = client.custom_query(query=query)
        return {"data": {"result": result}}
    except Exception as e:
        logger.error(f"Unexpected error querying Prometheus: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

def extract_metric_value(prometheus_response: Dict[str, Any], default: float = 0) -> float:
    """
    Extract a single value from a Prometheus response
    """
    if (prometheus_response and 'data' in prometheus_response and 
        'result' in prometheus_response['data'] and 
        len(prometheus_response['data']['result']) > 0):
        
        result = prometheus_response['data']['result'][0]
        if 'value' in result:
            return float(result['value'][1])
        
    return default

def extract_namespace_results(prometheus_response: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract namespace-specific results from a Prometheus response
    """
    results = {}
    
    if prometheus_response and 'data' in prometheus_response and 'result' in prometheus_response['data']:
        for item in prometheus_response['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace] = float(item['value'][1])
    
    return results

def push_to_prometheus(job: str = 'finops_api') -> bool:
    """
    Push metrics to Prometheus Pushgateway
    """
    try:
        from prometheus_client import push_to_gateway
        push_to_gateway(PUSHGATEWAY_URL, job=job, registry=None)
        logger.info(f"Successfully pushed metrics to Prometheus Pushgateway as job '{job}'")
        return True
    except Exception as e:
        logger.error(f"Failed to push metrics to Prometheus Pushgateway: {e}")
        return False