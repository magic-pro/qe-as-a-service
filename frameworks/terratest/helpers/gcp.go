// Package helpers provides shared utilities for Terratest infrastructure tests.
package helpers

import (
	"fmt"
	"math/rand"
	"os"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
)

// TerraformOptions returns base Terraform options for a given module path and environment.
func TerraformOptions(t *testing.T, modulePath, env string, vars map[string]interface{}) *terraform.Options {
	t.Helper()
	projectID := RequireEnv(t, "GCP_PROJECT_ID")
	region := EnvOrDefault("GCP_REGION", "europe-west2")

	baseVars := map[string]interface{}{
		"project_id": projectID,
		"region":     region,
		"environment": env,
	}
	for k, v := range vars {
		baseVars[k] = v
	}

	return &terraform.Options{
		TerraformDir: modulePath,
		Vars:         baseVars,
		NoColor:      true,
	}
}

// UniqueID returns a short unique suffix safe for GCP resource names.
func UniqueID() string {
	rand.Seed(time.Now().UnixNano()) //nolint:staticcheck
	return fmt.Sprintf("%06d", rand.Intn(999999)) //nolint:gosec
}

// RequireEnv fails the test if an environment variable is not set.
func RequireEnv(t *testing.T, key string) string {
	t.Helper()
	val := os.Getenv(key)
	require.NotEmptyf(t, val, "required env var %s is not set", key)
	return val
}

// EnvOrDefault returns the env var value or a default.
func EnvOrDefault(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}

// ApplyAndDefer applies a Terraform module and registers cleanup via t.Cleanup.
// Usage: opts := ApplyAndDefer(t, tfOpts)
func ApplyAndDefer(t *testing.T, opts *terraform.Options) *terraform.Options {
	t.Helper()
	terraform.InitAndApply(t, opts)
	t.Cleanup(func() {
		terraform.Destroy(t, opts)
	})
	return opts
}
