#!/bin/bash
# Cleanup script for FinOps setup

echo "Deleting FinOps API resources..."
kubectl delete -f kubernetes/finops-api.yaml --ignore-not-found=true

echo "Deleting Helm releases..."
helm uninstall opencost -n opencost --ignore-not-found
helm uninstall prometheus -n monitoring --ignore-not-found

echo "Deleting namespaces..."
kubectl delete namespace opencost --ignore-not-found=true
kubectl delete namespace monitoring --ignore-not-found=true
kubectl delete namespace finops --ignore-not-found=true

echo "Deleting Kind cluster..."
kind delete cluster --name finops-poc

# Remove entries from /etc/hosts
echo "Removing entries from /etc/hosts..."
sudo sed -i '/grafana prometheus alertmanager opencost opencost-api finops-api/d' /etc/hosts

echo "Cleanup complete!"