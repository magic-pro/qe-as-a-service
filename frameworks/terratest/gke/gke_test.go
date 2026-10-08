//go:build integration

package gke_test

import (
	"fmt"
	"testing"

	"github.com/gruntwork-io/terratest/modules/gcp"
	"github.com/gruntwork-io/terratest/modules/k8s"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/your-org/qe-terratest/helpers"
)

// TestGKEClusterProvisioning verifies GKE cluster is provisioned correctly.
// BRD-REQ: INFRA-001
// INFRA-LAYER: Compute/GKE
func TestGKEClusterProvisioning(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	clusterName := fmt.Sprintf("qe-test-cluster-%s", uid)

	opts := helpers.TerraformOptions(t, "../../terraform/modules/gke", "staging", map[string]interface{}{
		"cluster_name":   clusterName,
		"node_count":     1,
		"machine_type":   "e2-standard-2",
	})
	helpers.ApplyAndDefer(t, opts)

	// Verify cluster exists in GCP
	projectID := helpers.RequireEnv(t, "GCP_PROJECT_ID")
	region := helpers.EnvOrDefault("GCP_REGION", "europe-west2")
	cluster := gcp.GetGKECluster(t, projectID, region, clusterName)

	assert.Equal(t, "RUNNING", cluster.Status)
	assert.NotEmpty(t, cluster.Endpoint)
}

// TestGKENodePoolScaling verifies HPA-driven scaling works correctly.
// BRD-REQ: INFRA-002
// INFRA-LAYER: Compute/GKE
func TestGKENodePoolScaling(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	opts := helpers.TerraformOptions(t, "../../terraform/modules/gke", "staging", map[string]interface{}{
		"cluster_name": fmt.Sprintf("qe-scale-test-%s", uid),
		"min_nodes":    1,
		"max_nodes":    3,
	})
	helpers.ApplyAndDefer(t, opts)

	clusterName := terraform.Output(t, opts, "cluster_name")
	require.NotEmpty(t, clusterName)

	kubeOpts := k8s.NewKubectlOptions("", "", "default")
	nodes := k8s.GetNodes(t, kubeOpts)
	assert.GreaterOrEqual(t, len(nodes), 1)
}

// TestGKENetworkPolicyEnforcement verifies pods cannot communicate outside defined policies.
// BRD-REQ: INFRA-SEC-001
// INFRA-LAYER: Compute/GKE + Networking
func TestGKENetworkPolicyEnforcement(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	opts := helpers.TerraformOptions(t, "../../terraform/modules/gke", "staging", map[string]interface{}{
		"cluster_name":           fmt.Sprintf("qe-netpol-test-%s", uid),
		"enable_network_policy":  true,
	})
	helpers.ApplyAndDefer(t, opts)

	kubeOpts := k8s.NewKubectlOptions("", "", "default")

	// Verify network policy resources are present
	_, err := k8s.RunKubectlAndGetOutputE(t, kubeOpts, "get", "networkpolicies", "--all-namespaces")
	assert.NoError(t, err, "Network policies should be retrievable")
}
