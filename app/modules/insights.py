import os
import logging
from typing import List

from .models import ResourceData, CostEfficiency, Recommendation, CostAnomaly, CostForecast
from .prometheus import query_prometheus, extract_metric_value

from modules.metrics import *

logger = logging.getLogger(__name__)

# Environment variables with default values
CPU_HOURLY_COST = float(os.getenv("CPU_HOURLY_COST", "0.04"))
MEMORY_GB_HOURLY_COST = float(os.getenv("MEMORY_GB_HOURLY_COST", "0.01"))

def get_namespace_resources() -> List[ResourceData]:
    """
    Collect resource usage and allocation data for all namespaces
    """
    results = {}
    
    # Get CPU requests by namespace
    cpu_requests = query_prometheus(
        "sum(kube_pod_container_resource_requests{resource='cpu'}) by (namespace)"
    )
    
    # Get CPU usage by namespace
    cpu_usage = query_prometheus(
        "sum(rate(container_cpu_usage_seconds_total[1h])) by (namespace)"
    )
    
    # Get CPU limits by namespace
    cpu_limits = query_prometheus(
        "sum(kube_pod_container_resource_limits{resource='cpu'}) by (namespace)"
    )
    
    # Get memory requests by namespace
    memory_requests = query_prometheus(
        "sum(kube_pod_container_resource_requests{resource='memory'}) by (namespace) / 1024 / 1024 / 1024"
    )
    
    # Get memory usage by namespace
    memory_usage = query_prometheus(
        "sum(container_memory_working_set_bytes) by (namespace) / 1024 / 1024 / 1024"
    )
    
    # Get memory limits by namespace
    memory_limits = query_prometheus(
        "sum(kube_pod_container_resource_limits{resource='memory'}) by (namespace) / 1024 / 1024 / 1024"
    )
    
    # Get namespace cost
    namespace_costs = query_prometheus(
        """
        sum(
          (
            sum(container_memory_allocation_bytes) by (namespace)
            * on() group_left()
            (avg(node_ram_hourly_cost) / (1024 * 1024 * 1024) * 730)
          )
          +
          (
            sum(container_cpu_allocation) by (namespace)
            * on() group_left()
            (avg(node_cpu_hourly_cost) * 730)
          )
        ) by (namespace)
        """
    )
    
    # Process data for all namespaces
    all_namespaces = set()
    
    # Collect all unique namespaces
    for query_result in [cpu_requests, cpu_usage, cpu_limits, memory_requests, memory_usage, memory_limits, namespace_costs]:
        if query_result and 'data' in query_result and 'result' in query_result['data']:
            for item in query_result['data']['result']:
                if 'metric' in item and 'namespace' in item['metric']:
                    all_namespaces.add(item['metric']['namespace'])
    
    # Initialize data for all namespaces
    for namespace in all_namespaces:
        results[namespace] = {
            'cpu_request': 0,
            'cpu_usage': 0,
            'cpu_limit': 0,
            'memory_request': 0,
            'memory_usage': 0,
            'memory_limit': 0,
            'cost': 0
        }
    
    # Fill in CPU requests
    if cpu_requests and 'data' in cpu_requests and 'result' in cpu_requests['data']:
        for item in cpu_requests['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['cpu_request'] = float(item['value'][1])
    
    # Fill in CPU usage
    if cpu_usage and 'data' in cpu_usage and 'result' in cpu_usage['data']:
        for item in cpu_usage['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['cpu_usage'] = float(item['value'][1])
    
    # Fill in CPU limits
    if cpu_limits and 'data' in cpu_limits and 'result' in cpu_limits['data']:
        for item in cpu_limits['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['cpu_limit'] = float(item['value'][1])
    
    # Fill in memory requests
    if memory_requests and 'data' in memory_requests and 'result' in memory_requests['data']:
        for item in memory_requests['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['memory_request'] = float(item['value'][1])
    
    # Fill in memory usage
    if memory_usage and 'data' in memory_usage and 'result' in memory_usage['data']:
        for item in memory_usage['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['memory_usage'] = float(item['value'][1])
    
    # Fill in memory limits
    if memory_limits and 'data' in memory_limits and 'result' in memory_limits['data']:
        for item in memory_limits['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['memory_limit'] = float(item['value'][1])
    
    # Fill in namespace costs
    if namespace_costs and 'data' in namespace_costs and 'result' in namespace_costs['data']:
        for item in namespace_costs['data']['result']:
            if 'metric' in item and 'namespace' in item['metric'] and 'value' in item:
                namespace = item['metric']['namespace']
                results[namespace]['cost'] = float(item['value'][1])
    
    # Convert to list of ResourceData objects
    return [
        ResourceData(
            namespace=namespace,
            **data
        )
        for namespace, data in results.items()
    ]

def calculate_cost_efficiency(resource_data: ResourceData) -> CostEfficiency:
    """
    Calculate cost efficiency score (0-100) based on resource utilization
    """
    # Calculate wasted resources percentages
    wasted_cpu_percent = 0
    if resource_data.cpu_request > 0:
        wasted_cpu_percent = max(0, (resource_data.cpu_request - resource_data.cpu_usage) / resource_data.cpu_request * 100)
    
    wasted_memory_percent = 0
    if resource_data.memory_request > 0:
        wasted_memory_percent = max(0, (resource_data.memory_request - resource_data.memory_usage) / resource_data.memory_request * 100)
    
    # Calculate efficiency score - higher is better (less waste)
    # We weigh CPU and memory equally for the score
    efficiency_score = 100 - (wasted_cpu_percent + wasted_memory_percent) / 2
    
    # Ensure the score is between 0 and 100
    efficiency_score = max(0, min(100, efficiency_score))

    finops_efficiency_score.labels(exported_namespace=resource_data.namespace).set(efficiency_score)
    finops_resource_waste.labels(exported_namespace=resource_data.namespace, resource_type="cpu").set(wasted_cpu_percent)
    finops_resource_waste.labels(exported_namespace=resource_data.namespace, resource_type="memory").set(wasted_memory_percent)
    
    # Calculate and update usage ratios
    cpu_usage_ratio = resource_data.cpu_usage / resource_data.cpu_request if resource_data.cpu_request > 0 else 0
    memory_usage_ratio = resource_data.memory_usage / resource_data.memory_request if resource_data.memory_request > 0 else 0
    
    finops_resource_utilization.labels(exported_namespace=resource_data.namespace, resource_type="cpu").set(cpu_usage_ratio)
    finops_resource_utilization.labels(exported_namespace=resource_data.namespace, resource_type="memory").set(memory_usage_ratio)

    return CostEfficiency(
        namespace=resource_data.namespace,
        efficiency_score=efficiency_score,
        wasted_cpu_percent=wasted_cpu_percent,
        wasted_memory_percent=wasted_memory_percent
    )

def generate_recommendations(resource_data: ResourceData) -> List[Recommendation]:
    """
    Generate cost optimization recommendations based on resource utilization
    """
    recommendations = []
    
    # Check if CPU request can be optimized (if usage is much lower than request)
    if resource_data.cpu_request > 0 and resource_data.cpu_usage / resource_data.cpu_request < 0.7:
        # Recommend a value 30% higher than actual usage for safety
        recommended_cpu = max(0.1, resource_data.cpu_usage * 1.3)
        
        # Calculate savings
        monthly_cpu_savings = (resource_data.cpu_request - recommended_cpu) * CPU_HOURLY_COST * 730
        
        if monthly_cpu_savings > 1.0:  # Only recommend if savings are meaningful
            recommendations.append(
                Recommendation(
                    namespace=resource_data.namespace,
                    recommendation_type="cpu_request_rightsizing",
                    description=f"Reduce CPU requests to match actual usage plus a 30% buffer",
                    estimated_savings=monthly_cpu_savings,
                    current_value=resource_data.cpu_request,
                    recommended_value=recommended_cpu
                )
            )
    
    # Check if memory request can be optimized
    if resource_data.memory_request > 0 and resource_data.memory_usage / resource_data.memory_request < 0.7:
        # Recommend a value 30% higher than actual usage for safety
        recommended_memory = max(0.1, resource_data.memory_usage * 1.3)
        
        # Calculate savings
        monthly_memory_savings = (resource_data.memory_request - recommended_memory) * MEMORY_GB_HOURLY_COST * 730
        
        if monthly_memory_savings > 1.0:  # Only recommend if savings are meaningful
            recommendations.append(
                Recommendation(
                    namespace=resource_data.namespace,
                    recommendation_type="memory_request_rightsizing",
                    description=f"Reduce memory requests to match actual usage plus a 30% buffer",
                    estimated_savings=monthly_memory_savings,
                    current_value=resource_data.memory_request,
                    recommended_value=recommended_memory
                )
            )
    
    # Check for missing resource limits
    if resource_data.cpu_limit == 0 and resource_data.cpu_request > 0:
        recommendations.append(
            Recommendation(
                namespace=resource_data.namespace,
                recommendation_type="add_cpu_limits",
                description="Add CPU limits to prevent resource hogging",
                estimated_savings=0.0,  # No direct cost savings but improves cluster stability
                current_value="No limit",
                recommended_value=str(max(1, resource_data.cpu_request * 2))  # Recommend 2x the request
            )
        )
        
    if resource_data.memory_limit == 0 and resource_data.memory_request > 0:
        recommendations.append(
            Recommendation(
                namespace=resource_data.namespace,
                recommendation_type="add_memory_limits",
                description="Add memory limits to prevent resource hogging",
                estimated_savings=0.0,  # No direct cost savings but improves cluster stability
                current_value="No limit",
                recommended_value=str(max(1, resource_data.memory_request * 1.5))  # Recommend 1.5x the request
            )
        )
        
    for recommendation in recommendations:
        if isinstance(recommendation.estimated_savings, (int, float)):
            finops_optimization_savings.labels(
                exported_namespace=recommendation.namespace,
                recommendation_type=recommendation.recommendation_type
            ).set(recommendation.estimated_savings)
    
    return recommendations

def detect_cost_anomalies(namespace: str) -> CostAnomaly:
    """
    Detect unusual patterns in cost data compared to historical trends
    using statistical methods
    """
    # Get hourly cost data for the past 7 days
    hourly_cost_query = f"""
    sum(
      (
        sum(container_memory_allocation_bytes{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_ram_hourly_cost) / (1024 * 1024 * 1024) * 1)
      )
      +
      (
        sum(container_cpu_allocation{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_cpu_hourly_cost) * 1)
      )
    )[7d:1h]
    """
    
    # Get current cost
    current_cost_query = f"""
    sum(
      (
        sum(container_memory_allocation_bytes{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_ram_hourly_cost) / (1024 * 1024 * 1024) * 1)
      )
      +
      (
        sum(container_cpu_allocation{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_cpu_hourly_cost) * 1)
      )
    )
    """
    
    # Execute queries
    hourly_cost_data = query_prometheus(hourly_cost_query)
    current_cost_data = query_prometheus(current_cost_query)
    
    # Extract current cost
    current_cost = extract_metric_value(current_cost_data, default=0)
    
    # Process historical data for statistical analysis
    try:
        data_points = []
        if 'data' in hourly_cost_data and 'result' in hourly_cost_data['data'] and hourly_cost_data['data']['result']:
            for value in hourly_cost_data['data']['result'][0]['values']:
                data_points.append(float(value[1]))
            
            if len(data_points) > 24:  # Ensure we have at least a day of hourly data
                import numpy as np
                
                # Calculate mean and standard deviation
                mean_cost = np.mean(data_points)
                std_cost = np.std(data_points)
                
                # Calculate Z-score for current cost
                if std_cost > 0:
                    z_score = abs((current_cost - mean_cost) / std_cost)
                    
                    # Convert Z-score to anomaly score (0-100)
                    # Z-score of 2 (95% confidence) = 50% anomaly
                    # Z-score of 3 (99.7% confidence) = 100% anomaly
                    anomaly_score = min(100, max(0, (z_score - 1) * 50))
                else:
                    # If std is 0, we can't calculate z-score
                    anomaly_score = 0 if current_cost == mean_cost else 100
                
                increase_percent = ((current_cost - mean_cost) / mean_cost * 100) if mean_cost > 0 else 0
            else:
                # Not enough data points
                anomaly_score = 0
                increase_percent = 0
                mean_cost = current_cost
        else:
            # No data available
            anomaly_score = 0
            increase_percent = 0
            mean_cost = current_cost
            
    except Exception as e:
        logger.error(f"Error calculating cost anomalies: {e}")
        anomaly_score = 0
        increase_percent = 0
        mean_cost = current_cost
        
    finops_anomaly_score.labels(exported_namespace=namespace).set(anomaly_score)
    
    return CostAnomaly(
        namespace=namespace,
        usual_cost=mean_cost,
        current_cost=current_cost,
        increase_percent=increase_percent,
        anomaly_score=anomaly_score
    )

def generate_cost_forecast(namespace: str) -> CostForecast:
    """
    Generate a 30-day cost forecast based on historical data with improved methodology
    """
    # Get daily cost data for the past 30 days
    daily_cost_query = f"""
    sum(
      (
        sum(container_memory_allocation_bytes{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_ram_hourly_cost) / (1024 * 1024 * 1024) * 24)
      )
      +
      (
        sum(container_cpu_allocation{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_cpu_hourly_cost) * 24)
      )
    )[30d:1d]
    """
    
    daily_cost_data = query_prometheus(daily_cost_query)
    
    # Get current monthly cost
    current_cost_query = f"""
    sum(
      (
        sum(container_memory_allocation_bytes{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_ram_hourly_cost) / (1024 * 1024 * 1024) * 730)
      )
      +
      (
        sum(container_cpu_allocation{{namespace="{namespace}"}})
        * on() group_left()
        (avg(node_cpu_hourly_cost) * 730)
      )
    )
    """
    
    current_cost_data = query_prometheus(current_cost_query)
    current_cost = extract_metric_value(current_cost_data, default=0)
    
    # Analyze the historical data for trend
    # This is a simplified linear regression - in production, consider using numpy's polyfit
    try:
        data_points = []
        if 'data' in daily_cost_data and 'result' in daily_cost_data['data'] and daily_cost_data['data']['result']:
            for value in daily_cost_data['data']['result'][0]['values']:
                data_points.append(float(value[1]))
            
            if len(data_points) > 7:  # Ensure we have at least a week of data
                import numpy as np
                x = np.arange(len(data_points))
                y = np.array(data_points)
                slope, intercept = np.polyfit(x, y, 1)
                
                # Calculate trend as percentage
                trend_percent = (slope * 30 / current_cost) * 100 if current_cost > 0 else 0
                
                # Project forward using linear model
                forecasted_cost = current_cost * (1 + trend_percent/100)
            else:
                trend_percent = 0
                forecasted_cost = current_cost
        else:
            trend_percent = 0
            forecasted_cost = current_cost
            
    except Exception as e:
        logger.error(f"Error calculating cost forecast: {e}")
        trend_percent = 0
        forecasted_cost = current_cost
        
    finops_cost_forecast.labels(exported_namespace=namespace).set(forecasted_cost)
    
    return CostForecast(
        namespace=namespace,
        current_monthly_cost=current_cost,
        forecasted_monthly_cost=forecasted_cost,
        trend_percent=trend_percent
    )