# 🚀 Deployment Orchestration

This directory serves as the central hub for production-grade deployment artifacts. It provides standardized manifests for both **Amazon EKS (Kubernetes)** and **Docker Swarm**, ensuring high availability, scalability, and security across different orchestration environments.

---

## 📂 Directory Structure

| Artifact | Path | Description |
| --- | --- | --- |
| **EKS Manifest** | `eks/deployment.yaml` | Unified manifest including HPA, ALB Ingress, and NetworkPolicies. |
| **Swarm Stack** | `swarm/docker-swarm.yaml` | Production stack with defined deploy policies and resource constraints. |
| **Environment** | `env/production.env.required` | Template for mandatory production secrets and configurations. |
| **Stable Compose** | `compose/docker-compose.stable.yml` | Local/Staging reference using the LGTM observability stack. |

---

## 🛠 Preflight Checklist

Before initiating any rollout, ensure the following conditions are met to prevent deployment failure:

1. **Secret Provisioning:** Ensure all keys listed in `production.env.required` are present in **AWS Secrets Manager** (for EKS) or **Docker Secrets** (for Swarm).
2. **Connectivity:** Verify that the target runtime has a clear network path to external **Postgres** and **Redis** endpoints.
3. **Schema Management:** `server`, `BeNotified`, and `BeCertain` bootstrap schema on startup for fresh database deployments.


4. **Placeholder Review:** Search and replace all `TODO_*` strings within the manifests with environment-specific values.

---

---

## ☸️ EKS Deployment (Kubernetes)

The EKS deployment leverages the **AWS Load Balancer Controller** and **External Secrets Operator** for a cloud-native experience.

### Deployment Command

```bash
kubectl apply -f deployment/eks/deployment.yaml

```

### Validation & Health Checks

```bash
# Perform a dry-run to validate syntax
kubectl apply --dry-run=client -f deployment/eks/deployment.yaml

# Monitor rollout status
kubectl -n beobservant get pods,svc,ingress,hpa

```

### Infrastructure Assumptions

* **Ingress:** AWS Load Balancer Controller is active.
* **Secrets:** External Secrets Operator is installed.
* **Store:** A `ClusterSecretStore` named `aws-secretsmanager` must be pre-configured.

---

## 🐳 Docker Swarm Deployment

Designed for environments requiring simplified orchestration while maintaining robust service discovery and scaling.

### Deployment Command

```bash
docker stack deploy -c deployment/swarm/docker-swarm.yaml beobservant

```

### Validation & Health Checks

```bash
# Verify the resolved configuration
docker stack config -c deployment/swarm/docker-swarm.yaml

# Check service replication and health
docker stack services beobservant

```

---

## 🔐 Security & Environment

Configuration is strictly decoupled from the runtime. All required environment variables are documented in:
`deployment/env/production.env.required`

> [!IMPORTANT]
> Never commit actual `.env` files or plaintext secrets to this repository. Always use the integrated secret providers (Vault/Secrets Manager) as defined in the manifests.

Would you like me to generate a specific **GitHub Actions workflow** to automate these deployments based on these files?
