# P05 — public-lineage multi-observable Trellis reference

## Status

Experimental correctness reference only. This phase does **not** claim to reproduce or contain Google's private implementation.

## Public evidence

The frozen modern upstream baseline remains `024db1d3b5b038f565c476dd1b51885271f7b0bf`.

Public Trellis history contains an earlier implementation at `56996facf54c25e6c08fed19d8902f40e1971f55` whose wide path already carries a `uint64_t obs_mask` through each beam entry, XORs it with each fault's observable mask, merges entries by detector state plus observable mask, and ranks/prunes by detector-state mass. Its final reconstruction still only recognizes observable masks 0 and 1.

P05 uses that public ancestor as a semantic reference and changes only the missing final multi-observable reconstruction plus the public `decode()` projection of the resulting mask. It also adds an explicit 64-observable bound.

## Hypothesis

For a valid final detector state, the decoder should aggregate/retain probability mass by the complete logical observable mask and predict the maximum-mass joint mask. Beam truncation remains defined over detector states, not over individual logical masks.

This is intentionally a **joint-MAP mask** reference. It is not equivalent in general to decoding each logical observable independently.

## P05a acceptance contract

1. The modern frozen upstream baseline still builds and its original Trellis test suite passes unchanged.
2. The public ancestor is checked out at the exact pinned SHA.
3. The P05 patch applies only to the public ancestor and is preserved as an artifact diff.
4. A one-observable regression case retains the original behavior.
5. Hand-checkable two-observable decoding preserves a joint mask with multiple bits set.
6. Synthetic 8- and 12-observable DEMs preserve high logical bits.
7. Logical observable 63 is accepted and returned correctly; observable 64 is rejected, enforcing a maximum of 64 observables indexed 0..63.
8. No GitHub-hosted timing is treated as a scientific benchmark.

## Deliberate non-goals

- No claim of equivalence to any private branch.
- No use of Sinter.
- No performance conclusion from GitHub Actions.
- No attempt yet to port the reference semantics into the optimized modern `mass0/mass1` kernel.
- No modification of the original Tesseract decoder.

## Next step if P05a passes

Port the verified joint-mask semantics into a separate modern experimental path while preserving the current single-observable fast path byte-for-byte where practical. Differential tests should compare the modern experimental path against this P05 public-lineage reference before attempting the BB workloads.