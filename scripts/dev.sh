# Build and deploy the source code of the FinOps API
echo "Building FinOps API Docker Image..."
docker build -t finops-api:latest ./app/

# Load the image into Kind
echo "Loading FinOps API Docker Image into Kind..."
kind load docker-image finops-api:latest --name finops-poc

# Delete the existing pod
echo "Deleting existing pod..."
kubectl delete pods -l app=finops-api -n finops

