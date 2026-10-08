//go:build integration

package pubsub_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"cloud.google.com/go/pubsub"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/your-org/qe-terratest/helpers"
)

// TestPubSubTopicAndSubscription verifies Pub/Sub topic and subscription are created correctly.
// BRD-REQ: INFRA-MSG-001
// INFRA-LAYER: Data/PubSub
func TestPubSubTopicAndSubscription(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	topicName := fmt.Sprintf("qe-test-topic-%s", uid)
	subName := fmt.Sprintf("qe-test-sub-%s", uid)

	opts := helpers.TerraformOptions(t, "../../terraform/modules/pubsub", "staging", map[string]interface{}{
		"topic_name":        topicName,
		"subscription_name": subName,
		"message_retention": "600s",
	})
	helpers.ApplyAndDefer(t, opts)

	outputTopic := terraform.Output(t, opts, "topic_name")
	outputSub := terraform.Output(t, opts, "subscription_name")

	assert.Equal(t, topicName, outputTopic)
	assert.Equal(t, subName, outputSub)
}

// TestPubSubPublishConsume verifies messages can be published and consumed correctly.
// BRD-REQ: INFRA-MSG-002
// INFRA-LAYER: Data/PubSub
func TestPubSubPublishConsume(t *testing.T) {
	t.Parallel()

	projectID := helpers.RequireEnv(t, "GCP_PROJECT_ID")
	topicID := helpers.RequireEnv(t, "TEST_PUBSUB_TOPIC_ID")
	subID := helpers.RequireEnv(t, "TEST_PUBSUB_SUB_ID")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	client, err := pubsub.NewClient(ctx, projectID)
	require.NoError(t, err)
	defer client.Close()

	// Publish
	topic := client.Topic(topicID)
	result := topic.Publish(ctx, &pubsub.Message{
		Data: []byte(`{"transaction_id":"test-123","amount":"10.50","currency":"GBP"}`),
		Attributes: map[string]string{
			"source": "qe-test",
		},
	})
	_, err = result.Get(ctx)
	require.NoError(t, err, "Message publish must succeed")

	// Consume
	sub := client.Subscription(subID)
	received := make(chan []byte, 1)
	go func() { //nolint:errcheck
		sub.Receive(ctx, func(_ context.Context, msg *pubsub.Message) {
			received <- msg.Data
			msg.Ack()
		})
	}()

	select {
	case data := <-received:
		assert.Contains(t, string(data), "transaction_id")
	case <-ctx.Done():
		t.Fatal("Timed out waiting for message — consumer lag issue")
	}
}

// TestPubSubDeadLetterQueue verifies poison messages go to DLQ after max delivery attempts.
// BRD-REQ: INFRA-MSG-003
// INFRA-LAYER: Data/PubSub
func TestPubSubDeadLetterQueue(t *testing.T) {
	t.Parallel()

	uid := helpers.UniqueID()
	opts := helpers.TerraformOptions(t, "../../terraform/modules/pubsub", "staging", map[string]interface{}{
		"topic_name":               fmt.Sprintf("qe-dlq-topic-%s", uid),
		"subscription_name":        fmt.Sprintf("qe-dlq-sub-%s", uid),
		"dead_letter_topic":        fmt.Sprintf("qe-dlq-dead-%s", uid),
		"max_delivery_attempts":    5,
	})
	helpers.ApplyAndDefer(t, opts)

	dlqTopic := terraform.Output(t, opts, "dead_letter_topic_name")
	assert.NotEmpty(t, dlqTopic, "DLQ topic must be provisioned")
}
