# Create Kind cluster
echo "Creating Kind cluster..."
kind create cluster --name finops-poc --config kubernetes/kind-config.yaml

# Pre-load required images
echo "Pre-loading images..."
docker pull ghcr.io/opencost/opencost:1.114.0
docker pull ghcr.io/opencost/opencost-ui:1.114.0
kind load docker-image ghcr.io/opencost/opencost:1.114.0 --name finops-poc
kind load docker-image ghcr.io/opencost/opencost-ui:1.114.0 --name finops-poc


# Create namespaces
kubectl create namespace finops
kubectl create namespace monitoring
kubectl create namespace opencost

# Install ingress-nginx
echo "Installing NGINX Ingress Controller..."
kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/deploy-ingress-nginx.yaml

# Wait for ingress controller to be ready, as shown in the docs
echo "Waiting for ingress controller to be ready..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=90s

# Create a configmap for the custom Grafana dashboards
kubectl create configmap custom-grafana-dashboards \
  --from-file=grafana/dashboards/ \
  -n monitoring

# Label the configmap with the expected label
kubectl label configmap custom-grafana-dashboards grafana_dashboard=1 -n monitoring

# Install OpenCost and Prometheus Stack
echo "Adding Helm repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update

# Install Prometheus Stack (includes Grafana and AlertManager)
echo "Installing Prometheus Stack (Prometheus, Grafana, AlertManager)..."
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f values.yaml

echo "Waiting for Prometheus components to start..."
kubectl wait --for=condition=available --timeout=300s deployment/prometheus-kube-prometheus-operator -n monitoring

# Installing OpenCost
helm install opencost opencost/opencost \
  --namespace opencost --create-namespace \
  --set opencost.prometheus.internal.namespaceName="monitoring" \
  --set opencost.prometheus.internal.port=9090 \
  --set opencost.prometheus.internal.serviceName="prometheus-kube-prometheus-prometheus" \
  --set opencost.metrics.serviceMonitor.enabled="true" \
  --set opencost.metrics.serviceMonitor.additionalLabels.release=prometheus

echo "Waiting for OpenCost to start..."
kubectl wait --for=condition=available --timeout=300s deployment/opencost -n opencost   

# Apply FinOps alert rules
echo "Applying FinOps alert rules..."
kubectl apply -f finops-alerts.yml

# Wait for ingress controller to be ready
echo "Waiting for ingress controller to be ready..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=90s

# Apply Ingress configuration
echo "Applying Ingress configuration..."
kubectl apply -f kubernetes/opencost.yaml
kubectl apply -f kubernetes/monitoring.yaml

# Apply PVC test resources
echo "Deploying PVC test resources..."
kubectl apply -f pvc-test.yaml

# Verify PVC test was successful
echo "Checking PVC test status..."
kubectl wait --for=condition=Ready pod/pod-using-pvc -n monitoring --timeout=60s
if [ $? -eq 0 ]; then
    echo "PVC test successful, pod is running"
else
    echo "Warning: PVC test pod is not ready, may need troubleshooting"
fi

# Build and deploy the source code of the FinOps API
echo "Building FinOps API Docker Image..."
docker build -t finops-api:latest ./app/

# Load the image into Kind
echo "Loading FinOps API Docker Image into Kind..."
kind load docker-image finops-api:latest --name finops-poc

# Deploy FinOps API
echo "Deploying FinOps API to Kubernetes..."
kubectl apply -f kubernetes/finops-api.yaml

# Wait for FinOps API to be ready
echo "Waiting for FinOps API to be ready for use..."
kubectl wait --for=condition=available --timeout=300s deployment/finops-api -n finops

# Add the hosts to /etc/hosts
echo "Adding hosts to /etc/hosts..."
NODE_IP=$(kubectl get nodes -o wide | awk 'NR==2{print $6}')
HOSTS_ENTRY="$NODE_IP grafana prometheus alertmanager opencost opencost-api finops-api"

# Check if the entry already exists
if ! grep -q "grafana prometheus alertmanager opencost opencost-api finops-api" /etc/hosts; then
    echo "$HOSTS_ENTRY" | sudo tee -a /etc/hosts
else
    echo "Hosts entry already exists, skipping..."
fi

# Get the Grafana password
GRAFANA_PASSWORD=$(kubectl --namespace monitoring get secrets prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d ; echo)

echo "Setup complete!"
echo ""
echo "To access Grafana:"
echo "http://grafana"
echo "Username: admin"
echo "Password: $GRAFANA_PASSWORD"
echo ""
echo "To access OpenCost UI:"
echo "http://opencost"
echo ""
echo "To access OpenCost API:"
echo "http://opencost-api"
echo ""
echo "To access Prometheus:"
echo "http://prometheus"
echo ""
echo "To access Alertmanager:"
echo "http://alertmanager"
echo ""
echo "FinOps Enhanced API deployment complete!"
echo ""
echo "Access the API at: http://finops-api:8000"
echo "API Documentation: http://finops-api:8000/docs"
echo ""
echo "Try these endpoints:"
echo "- /cost-efficiency        - Get cost efficiency scores by namespace"
echo "- /recommendations        - Get cost optimization recommendations"
echo "- /cost-anomalies         - Get cost anomaly detection results"
echo "- /all-insights           - Get all insights in one call"
echo "- /update-metrics         - Force an update of the Prometheus metrics"
echo ""
echo "Custom metrics are available in Prometheus under these names:"
echo "- finops_efficiency_score - Cost efficiency score by namespace (0-100%)"
echo "- finops_resource_waste - Percentage of wasted resources by type and namespace"
echo "- finops_anomaly_score - Cost anomaly detection score by namespace"
echo "- finops_optimization_savings - Potential monthly cost savings by recommendation type"
echo "- finops_resource_utilization - Resource utilization ratio by type and namespace"