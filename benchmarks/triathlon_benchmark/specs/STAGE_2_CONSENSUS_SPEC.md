# Stage 2 Specification: Distributed Consensus & Fault Tolerance (Raft + 2PC)

## Objective
Implement a multi-node distributed consensus cluster with Raft leader election, monotonic term tracking, log replication, and a Two-Phase Commit (2PC) transaction coordinator with **Term-Fencing** and partition tolerance under simulated network splits.

## Architecture & Required Modules (`stage2_consensus/src/`)

### 1. `rpc_network.py`
- Class `NetworkPartitionError(Exception)`
- Class `RPCNetwork`:
  - `register_node(node_id: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]])`
  - `send_rpc(sender: str, recipient: str, msg: Dict[str, Any]) -> Dict[str, Any]`
  - `isolate_partition(partition_nodes: Set[str])`: Creates bidirectional network partition.
  - `heal_partitions()`: Restores full network connectivity.
  - `drop_rate: float`: Simulates random packet drops.

### 2. `raft_node.py`
- Class `TermTracker`:
  - Monotonic term counter, `voted_for` persistence, quorum check.
- Class `RaftNode`:
  - `state`: `"FOLLOWER"`, `"CANDIDATE"`, `"LEADER"`
  - `start_election() -> bool`: Increments term, requests votes from peers across network. Transitions to `"LEADER"` only if majority quorum achieved.
  - `handle_rpc(msg: Dict[str, Any]) -> Dict[str, Any]`:
    - Handles `REQUEST_VOTE` and `APPEND_ENTRIES`.
    - Enforces term matching: if message term > current_term, step down to FOLLOWER and adopt new term.
    - Rejects append if message term < current_term.
  - `append_entry(command: Dict[str, Any]) -> int`: Adds entry to leader log with index and term.

### 3. `two_phase_commit.py`
- Class `SplitBrainConsensusException(Exception)`
- Class `TwoPhaseCommitCoordinator`:
  - `begin_transaction(tx_id: str) -> str`
  - `prepare(tx_id: str, participants: List[str], operations: List[Dict[str, Any]]) -> bool`:
    - Contacts all participant nodes.
    - Acquires term-fenced lock leases on target keys with TTL.
    - Records term at prepare time.
  - `commit(tx_id: str) -> bool`:
    - Verifies term fencing: checks whether any participant has transitioned to a higher term.
    - If a term mismatch or SplitBrain occurs: immediately releases all acquired lock leases, aborts the transaction cleanly, and raises `TransactionAbortedException`.
    - If successful: replicates commits to all participants and releases locks.
  - `abort(tx_id: str) -> bool`:
    - Releases all held locks for transaction and marks aborted.

### 4. `linearizability_checker.py`
- Class `LinearizabilityChecker`:
  - Records history of operations `(client, op_type, key, val, start_time, end_time)`.
  - Verifies that all observed reads are sequentially consistent with the latest acknowledged write, even during and after network partition heals.
