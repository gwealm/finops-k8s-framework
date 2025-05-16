#!/bin/bash
# deploy-to-aws.sh - Deploy FinOps framework to an existing AWS EKS cluster

# Ensure script exits on any error
set -e

# Configuration variables
NAMESPACE_FINOPS="finops"
NAMESPACE_MONITORING="monitoring"
NAMESPACE_OPENCOST="opencost"
AWS_REGION=$(aws configure get region)
EKS_CLUSTER_NAME=$(kubectl config current-context | cut -d'/' -f2)

echo "========================================="
echo "Deploying FinOps Framework to AWS EKS"
echo "Cluster: $EKS_CLUSTER_NAME (Region: $AWS_REGION)"
echo "========================================="

# Create namespaces
echo "Creating namespaces..."
kubectl create namespace $NAMESPACE_FINOPS --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace $NAMESPACE_MONITORING --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace $NAMESPACE_OPENCOST --dry-run=client -o yaml | kubectl apply -f -

# Create a configmap for the custom Grafana dashboards
kubectl create configmap custom-grafana-dashboards \
  --from-file=grafana/dashboards/ \
  -n $NAMESPACE_MONITORING \
  --dry-run=client -o yaml | kubectl apply -f -

# Label the configmap with the expected label
kubectl label configmap custom-grafana-dashboards grafana_dashboard=1 -n $NAMESPACE_MONITORING --overwrite

# Install OpenCost and Prometheus Stack
echo "Adding Helm repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm repo update


# Install Prometheus Stack with the correct values file
echo "Installing Prometheus Stack (Prometheus, Grafana, AlertManager)..."
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace $NAMESPACE_MONITORING \
  -f values.yaml

echo "Waiting for Prometheus components to start..."
kubectl wait --for=condition=available --timeout=300s deployment/prometheus-kube-prometheus-operator -n $NAMESPACE_MONITORING

# Extract node instance details for AWS pricing
echo "Determining EC2 instance types in the cluster..."
NODE_INSTANCE_TYPES=$(kubectl get nodes -o jsonpath='{.items[*].metadata.labels.node\.kubernetes\.io/instance-type}' | tr ' ' '\n' | sort | uniq | tr '\n' ',' | sed 's/,$//')
echo "Detected instance types: $NODE_INSTANCE_TYPES"

# Installing OpenCost with AWS cloud integration
echo "Installing OpenCost with AWS cloud integration..."
# Installing OpenCost
helm install opencost opencost/opencost \
  --namespace $NAMESPACE_OPENCOST \
  --set opencost.prometheus.internal.namespaceName="monitoring" \
  --set opencost.prometheus.internal.port=9090 \
  --set opencost.prometheus.internal.serviceName="prometheus-kube-prometheus-prometheus" \
  --set opencost.metrics.serviceMonitor.enabled="true" \
  --set opencost.metrics.serviceMonitor.additionalLabels.release=prometheus


echo "Waiting for OpenCost to start..."
kubectl wait --for=condition=available --timeout=300s deployment/opencost -n $NAMESPACE_OPENCOST

# Apply FinOps alert rules
echo "Applying FinOps alert rules..."
kubectl apply -f kubernetes/finops-alerts.yaml

# Apply LoadBalancer services for external access
echo "Creating service configuration for external access..."

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


# Build and deploy the FinOps API
echo "Building FinOps API Docker Image..."
docker build -t finops-api:latest ./app/

# Create an ECR repository for the FinOps API if it doesn't exist
ECR_REPO_NAME="finops-api"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
ECR_REPO_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"

echo "Checking for ECR repository..."
if ! aws ecr describe-repositories --repository-names $ECR_REPO_NAME 2>/dev/null; then
    echo "Creating ECR repository: $ECR_REPO_NAME"
    aws ecr create-repository --repository-name $ECR_REPO_NAME
fi

# Log in to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Tag and push the image to ECR
echo "Tagging and pushing FinOps API image to ECR..."
docker tag finops-api:latest $ECR_REPO_URI:latest
docker push $ECR_REPO_URI:latest

# Create and apply the FinOps API deployment with the ECR image
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: finops-api
  namespace: $NAMESPACE_FINOPS
  labels:
    app: finops-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: finops-api
  template:
    metadata:
      labels:
        app: finops-api
    spec:
      containers:
      - name: finops-api
        image: $ECR_REPO_URI:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
        env:
        - name: PROMETHEUS_URL
          value: "http://prometheus-kube-prometheus-prometheus.$NAMESPACE_MONITORING.svc.cluster.local:9090"
        - name: OPENCOST_URL
          value: "http://opencost.$NAMESPACE_OPENCOST.svc.cluster.local:9003"
        - name: GRAFANA_URL
          value: "http://prometheus-grafana.$NAMESPACE_MONITORING.svc.cluster.local:3000"
        - name: CPU_HOURLY_COST
          value: "0.04"
        - name: MEMORY_GB_HOURLY_COST
          value: "0.01"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: finops-api
  namespace: $NAMESPACE_FINOPS
spec:
  selector:
    app: finops-api
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  type: ClusterIP
---
apiVersion: v1
kind: Service
metadata:
  name: finops-api-lb
  namespace: $NAMESPACE_FINOPS
spec:
  selector:
    app: finops-api
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
  type: LoadBalancer
EOF

echo "Waiting for FinOps API to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/finops-api -n $NAMESPACE_FINOPS

# Wait for LoadBalancer services to get external IPs/hostnames
echo "Waiting for LoadBalancer endpoints to be assigned..."
sleep 30

# Get service endpoints
GRAFANA_ENDPOINT=$(kubectl get svc grafana-lb -n $NAMESPACE_MONITORING -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
PROMETHEUS_ENDPOINT=$(kubectl get svc prometheus-lb -n $NAMESPACE_MONITORING -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
ALERTMANAGER_ENDPOINT=$(kubectl get svc alertmanager-lb -n $NAMESPACE_MONITORING -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
OPENCOST_UI_ENDPOINT=$(kubectl get svc opencost-ui-lb -n $NAMESPACE_OPENCOST -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
OPENCOST_API_ENDPOINT=$(kubectl get svc opencost-api-lb -n $NAMESPACE_OPENCOST -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
FINOPS_API_ENDPOINT=$(kubectl get svc finops-api-lb -n $NAMESPACE_FINOPS -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Get the Grafana admin password
GRAFANA_PASSWORD=$(kubectl --namespace $NAMESPACE_MONITORING get secrets prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d)

echo "========================================="
echo "FinOps Framework Deployment Complete!"
echo "========================================="
echo ""
echo "ACCESS INFORMATION:"
echo ""
echo "Grafana:"
echo "  URL: http://$GRAFANA_ENDPOINT:3000"
echo "  Username: admin"
echo "  Password: $GRAFANA_PASSWORD"
echo ""
echo "Prometheus:"
echo "  URL: http://$PROMETHEUS_ENDPOINT:9090"
echo ""
echo "Alertmanager:"
echo "  URL: http://$ALERTMANAGER_ENDPOINT:9093"
echo ""
echo "OpenCost UI:"
echo "  URL: http://$OPENCOST_UI_ENDPOINT:9090"
echo ""
echo "OpenCost API:"
echo "  URL: http://$OPENCOST_API_ENDPOINT:9003"
echo ""
echo "FinOps API:"
echo "  URL: http://$FINOPS_API_ENDPOINT:80"
echo "========================================="
echo "NOTE: It may take a few minutes for DNS to propagate and for all services to be fully available."
echo "========================================="