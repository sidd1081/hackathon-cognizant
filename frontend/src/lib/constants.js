export const NOT_DOCUMENTED = "Not explicitly documented.";

// Must match backend/app/api/routes/dataset.py's _MAX_UPLOAD_BYTES. Kept below
// Cloud Run's hard 32 MB (33,554,432 byte) request-body ceiling so oversized
// uploads are caught here — with a clear message — instead of failing as an
// opaque platform-level connection error after the user waits for the upload.
export const MAX_UPLOAD_BYTES = 31 * 1024 * 1024;
export const MAX_UPLOAD_MB = MAX_UPLOAD_BYTES / (1024 * 1024);

// Verified example incidents — each retrieves its target ticket at (or near)
// rank 1 and produces a grounded, cited RCA on the current dataset. They span
// multiple Apache projects so "Use example" demonstrates cross-project coverage.
// See TEST_CASES.md for the full list with expected tickets/confidence.
export const EXAMPLE_INCIDENTS = [
  // Kafka — KAFKA-13122 (High)
  "A Kafka Streams app leaks resources because KeyValueIterator objects returned from state store queries are never closed after use.",
  // Solr — SOLR-15273 (High)
  "A distributed grouped query in Solr throws a NullPointerException when the unique key field has been renamed.",
  // Spark — SPARK-36067 (High)
  "Running the Spark YarnClusterSuite integration tests throws NoClassDefFoundError unless the hadoop-3.2 build profile is explicitly activated.",
  // ZooKeeper — ZOOKEEPER-4325 (High)
  "Calling ZkUtil listSubTreeBFS on the root path throws an IllegalArgumentException because an invalid path with an empty node name is generated.",
  // HBase — HBASE-26088 (Medium)
  "Repeatedly calling Connection.getBufferedMutator for a table leaks thread pool executors and never releases them.",
];

// First example is the default (also used as the textarea placeholder hint).
export const EXAMPLE_INCIDENT = EXAMPLE_INCIDENTS[0];
