# Test Cases — Incident RCA Assistant

Verified queries for demoing and testing the RCA assistant against the current
dataset (3,000 incidents across 8 Apache projects). Queries are **paraphrases**
(not copied ticket titles), so they exercise real semantic matching rather than
keyword lookup.

- **Grounded** cases retrieve their target ticket at (or near) rank 1 and produce
  a cited, evidence-grounded RCA.
- **Abstention** cases correctly return *"Not explicitly documented."* — the
  anti-hallucination guardrail refusing to invent an answer.

Confidence values are from actual runs; retrieval-only cases are marked
"retrieves #1" (target ticket verified at rank 1, confidence may vary by run).

> How to run: start the backend (`uv run uvicorn app.main:app --port 8000` from
> `backend/`), open the frontend, paste a query into **Ask Query**, and click
> **Analyze Incident**. The **Use example** button cycles through the ★ queries.

---

## 1. Primary demo queries (★ = in "Use example")

These are the strongest cross-project examples — grounded, cited, high/medium
confidence.

### ★ Kafka — resource leak (expected: KAFKA-13122, **High**)
```
A Kafka Streams app leaks resources because KeyValueIterator objects returned from state store queries are never closed after use.
```
Expected root cause: KeyValueIterator instances are not closed → resource leak.
Resolution: close each iterator (e.g. try-with-resources).

### ★ Solr — distributed grouped query NPE (expected: SOLR-15273, **High**)
```
A distributed grouped query in Solr throws a NullPointerException when the unique key field has been renamed.
```
Expected root cause: `StoredFieldsShardResponseProcessor` doesn't handle renamed
unique key fields. Resolution: upgrade to Solr 8.9.0+.

### ★ Spark — YarnClusterSuite NoClassDefFoundError (expected: SPARK-36067, **High**)
```
Running the Spark YarnClusterSuite integration tests throws NoClassDefFoundError unless the hadoop-3.2 build profile is explicitly activated.
```

### ★ ZooKeeper — listSubTreeBFS on root (expected: ZOOKEEPER-4325, **High**)
```
Calling ZkUtil listSubTreeBFS on the root path throws an IllegalArgumentException because an invalid path with an empty node name is generated.
```

### ★ HBase — BufferedMutator executor leak (expected: HBASE-26088, **Medium**)
```
Repeatedly calling Connection.getBufferedMutator for a table leaks thread pool executors and never releases them.
```

---

## 2. More verified queries by project

### Kafka
- **KAFKA-13100 (retrieves #1)** — controller / in-memory snapshot
  ```
  The Kafka controller cannot revert to an in-memory snapshot and ends up renouncing leadership.
  ```
- **KAFKA-9815 (Medium)** — consumer stuck after broker restart
  ```
  Kafka consumers stopped processing messages after a broker restart. The consumer group appears stuck, consumer lag keeps growing, and no messages are being consumed even though all brokers are healthy.
  ```

### Cassandra
- **CASSANDRA-16796 (High)** — pending ranges for a shutdown peer
  ```
  When a moving node crashes hard, stale pending ranges remain for the shutdown peer and block a later node replacement.
  ```
- **CASSANDRA-16752 (retrieves #1)** — flaky dtest after node restart
  ```
  Python dtest queries executed right after restarting a node sometimes fail because node state propagation is not awaited.
  ```

### Hadoop
- **HADOOP-17621 (Medium)** — hadoop-auth jetty-server dependency
  ```
  The hadoop-auth module should drop its jetty-server dependency because Jetty blocks loading jetty-server classes inside web applications.
  ```

### Spark
- **SPARK-35673 (retrieves #1)** — unrecognized hint in subquery
  ```
  Spark fails with an error when an unrecognized hint is used inside a subquery.
  ```
- **SPARK-35602 (retrieves #1)** — UTFDataFormatException writing state schema
  ```
  A Spark job crashes with java.io.UTFDataFormatException: encoded string too long when writing the state schema file.
  ```

### Solr
- **SOLR-15233 (retrieves #1)** — internode auth plugin broken
  ```
  Solr ConfigurableInternodeAuthHadoopPlugin with authorization is broken because requests are not forwarded correctly for all query types.
  ```

### HBase
- **HBASE-26036 (retrieves #1)** — direct byte buffer released too early
  ```
  HBase returns dirty data for some operations because a direct byte buffer is released too early.
  ```

### ZooKeeper
- **ZOOKEEPER-4311 (retrieves #1)** — fsync errors ignored
  ```
  ZooKeeper ignores fsync errors in AtomicFileWritingIdiom, deleting the tmp file without updating the main file.
  ```

---

## 3. Abstention test (should NOT answer)

The assistant should return *"Not explicitly documented."* with **Low**
confidence and cite nothing — proving it does not hallucinate.

### Out-of-domain (expected: abstain)
```
The office coffee machine is leaking water onto the break-room floor.
```
Top similarity ≈ 0.26 (below the relevance floor) → correctly abstains.

---

## 4. Known limitation (abstains — no substantive evidence)

This looks Kafka-related but the only ticket mentioning the mechanism
(KAFKA-13106) has "InvalidRequestException" only in an answer field (not embedded,
by design) and no substantive documented fix — so the assistant honestly
abstains rather than inventing a cause. Useful to show the guardrail is strict.

```
The Kafka consumer throws an InvalidRequestException with an unknown API key when it uses an offset-related administrative protocol not supported by the broker version.
```

---

## Benchmark summary (latest `scripts/evaluate.py` run)

| Metric | Result |
|---|---|
| Recall@5 | 0.875 |
| MRR | 0.875 |
| Root-cause correctness | 0.78 |
| Evidence-support rate | 1.0 |
| Hallucination rate | 0.0 |
| Abstention-correct (out-of-domain) | 1.0 |

Regenerate with: `cd backend && uv run python -m scripts.evaluate`
