from prometheus_client import Gauge, Counter

# Basic API metrics
finops_http_requests_total = Counter(
    'finops_http_requests_total', 
    'Total number of HTTP requests to FinOps API',
    ['method', 'endpoint', 'status']
)

# FinOps specific metrics
finops_efficiency_score = Gauge(
    'finops_efficiency_score', 
    'Cost efficiency score for namespaces (0-100, higher is better)', 
    ['exported_namespace']
)

finops_resource_waste = Gauge(
    'finops_resource_waste', 
    'Percentage of wasted resources (0-100, lower is better)', 
    ['exported_namespace', 'resource_type']
)

finops_anomaly_score = Gauge(
    'finops_anomaly_score', 
    'Score indicating unusual cost patterns (0-100, higher means more anomalous)', 
    ['exported_namespace']
)

finops_optimization_savings = Gauge(
    'finops_optimization_savings', 
    'Estimated monthly savings from optimization ($)', 
    ['exported_namespace', 'recommendation_type']
)

finops_cost_forecast = Gauge(
    'finops_cost_forecast', 
    '30-day cost forecast ($)', 
    ['exported_namespace']
)

finops_resource_utilization = Gauge(
    'finops_resource_utilization',
    'Ratio of actual usage vs requested resources (ideal ~0.7-0.8)',
    ['exported_namespace', 'resource_type']
)