# Kubernetes FinOps Framework

A FinOps (Financial Operations) framework built on top of OpenCost for Kubernetes cost optimization and monitoring.

## Overview

This framework extends OpenCost capabilities with additional FinOps metrics and insights, helping organizations optimize their Kubernetes spending through real-time monitoring, anomaly detection, forecasting, and optimization recommendations.

## Features

- **Cost efficiency scoring** across namespaces, pods, and containers
- **Resource optimization recommendations** to rightsize workloads
- **Cost anomaly detection** to identify unusual spending patterns
- **Custom Prometheus metrics** and Grafana dashboards

## Components

- **OpenCost**: Base cost allocation engine for Kubernetes
- **Prometheus & Grafana**: Metrics storage and visualization
- **AlertManager**: Alert handling and notification
- **FinOps API**: Custom middleware that provides enhanced metrics and insights

## Metrics

- `finops_efficiency_score`: Cost efficiency score by namespace (0-100%)
- `finops_resource_waste`: Percentage of wasted resources
- `finops_anomaly_score`: Cost anomaly detection score
- `finops_optimization_savings`: Potential monthly cost savings

## Installation

### Local Installation with Kind
```bash
# Clone the repository and run setup
git clone https://github.com/yourusername/finops-framework.git
cd finops-framework
./setup.sh
```

### Installation with AWS
```bash
# Clone the repository and run setup
git clone https://github.com/yourusername/finops-framework.git
cd finops-framework
./setup-aws.sh
```

## API Endpoints

- `/cost-efficiency`: Get cost efficiency scores
- `/recommendations`: Get optimization recommendations
- `/cost-anomalies`: Get anomaly detection results
- `/all-insights`: Get all insights in one call