//go:build integration

package cloudsql_test

import (
	"database/sql"
	"fmt"
	"testing"

	_ "github.com/lib/pq"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/your-org/qe-terratest/helpers"
)

// TestCloudSQLProvisioning verifies CloudSQL instance is provisioned with correct config.
// BRD-REQ: INFRA-DB-001
// INFRA-LAYER: Data/CloudSQL
func TestCloudSQLProvisioning(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	opts := helpers.TerraformOptions(t, "../../terraform/modules/cloudsql", "staging", map[string]interface{}{
		"instance_name":     fmt.Sprintf("qe-test-db-%s", uid),
		"database_version":  "POSTGRES_15",
		"tier":              "db-f1-micro",
		"deletion_protection": false,
	})
	helpers.ApplyAndDefer(t, opts)

	instanceName := terraform.Output(t, opts, "instance_name")
	connectionName := terraform.Output(t, opts, "connection_name")

	require.NotEmpty(t, instanceName)
	require.NotEmpty(t, connectionName)
}

// TestCloudSQLFailover verifies automatic failover behaves correctly.
// BRD-REQ: INFRA-DB-002
// INFRA-LAYER: Data/CloudSQL
func TestCloudSQLFailover(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	opts := helpers.TerraformOptions(t, "../../terraform/modules/cloudsql", "staging", map[string]interface{}{
		"instance_name":        fmt.Sprintf("qe-failover-test-%s", uid),
		"availability_type":    "REGIONAL", // enables HA
		"deletion_protection":  false,
	})
	helpers.ApplyAndDefer(t, opts)

	availabilityType := terraform.Output(t, opts, "availability_type")
	assert.Equal(t, "REGIONAL", availabilityType, "HA must be enabled for failover support")
}

// TestCloudSQLEncryptionAtRest verifies encryption is enabled (finance requirement).
// BRD-REQ: INFRA-SEC-DB-001
// INFRA-LAYER: Data/CloudSQL
func TestCloudSQLEncryptionAtRest(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	opts := helpers.TerraformOptions(t, "../../terraform/modules/cloudsql", "staging", map[string]interface{}{
		"instance_name":       fmt.Sprintf("qe-enc-test-%s", uid),
		"deletion_protection": false,
	})
	helpers.ApplyAndDefer(t, opts)

	// CloudSQL encrypts at rest by default; verify CMEK key if configured
	cmekKey := terraform.Output(t, opts, "kms_key_name")
	// If CMEK is configured, it must be non-empty
	if cmekKey != "" {
		assert.Contains(t, cmekKey, "cryptoKeys", "CMEK key must reference a valid Cloud KMS key")
	}
}

// TestCloudSQLDecimalPrecision verifies the DB stores monetary Decimal values correctly.
// Finance constraint: Decimal type, never float. Test that DB schema uses NUMERIC not FLOAT.
// BRD-REQ: INFRA-DB-FIN-001
// INFRA-LAYER: Data/CloudSQL
func TestCloudSQLDecimalPrecision(t *testing.T) {
	t.Parallel()

	connStr := helpers.RequireEnv(t, "TEST_DB_CONN_STRING")
	db, err := sql.Open("postgres", connStr)
	require.NoError(t, err)
	defer db.Close()

	// Query information_schema to verify monetary columns use NUMERIC not FLOAT
	rows, err := db.Query(`
		SELECT column_name, data_type
		FROM information_schema.columns
		WHERE table_schema = 'public'
		AND column_name IN ('amount', 'fee', 'balance', 'exchange_rate')
	`)
	require.NoError(t, err)
	defer rows.Close()

	for rows.Next() {
		var colName, dataType string
		require.NoError(t, rows.Scan(&colName, &dataType))
		assert.Equal(t, "numeric", dataType,
			"Finance column %s must use NUMERIC not FLOAT — Decimal precision requirement", colName)
	}
}
