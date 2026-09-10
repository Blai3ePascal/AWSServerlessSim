# P05b — adversarial validation of our public-lineage multi-observable reference

## What this phase is

P05a proved that our reconstructed public-lineage reference builds and handles 1, 2, 8, 12 and 64 observables. P05b tries to break it on purpose.

This is still **our experimental reconstruction from public code**. It is not claimed to be Google's private 64-observable implementation.

## Why these tests matter

The easy mistake would be to make something that merely accepts `L0..L63` syntactically but gets the probability semantics wrong. P05b therefore tests behavior, not just parsing.

### 1. XOR cancellation

Two faults that both flip the same logical observable must cancel when both happen. The test uses two high-probability `L3` faults, making the most likely joint event `L3 XOR L3 = 0`.

### 2. Competing logical explanations for the same syndrome

Two different logical masks can explain the same detector syndrome. The decoder must keep their separate masses and choose the higher joint mass, not simply the first path found.

### 3. Joint-MAP versus independent-bit decoding

This is the important one. There are distributions where the most likely complete logical mask is not what we would get by deciding each logical bit independently. The test constructs such a conditioned distribution explicitly and checks that our decoder returns the joint-MAP mask.

### 4. Deterministic tie breaking

If two complete logical masks have exactly the same mass, the reference chooses the numerically smaller mask. This is not claimed to be a private-upstream policy; it is a deterministic policy for our reference so repeated runs cannot randomly disagree.

### 5. Logical-only faults

A logical observable can flip without a detector firing. The implementation must still carry and reconstruct that logical mask correctly.

### 6. Exact exhaustive oracle

A tiny model with five independent faults, two detectors and three observables is small enough to enumerate every possible fault assignment exactly. For each of the four possible detector syndromes, the test computes the exact posterior mass of every observable mask and compares our Trellis result with the exact joint-MAP answer.

This is stronger than another hand-picked expected value because the expected result is computed independently from the Trellis implementation.

## Acceptance contract

P05b passes only if:

1. P05a patch still applies cleanly.
2. All P05a tests still pass.
3. All six adversarial P05b tests pass.
4. The exact enumerator agrees with Trellis for every syndrome in the tiny oracle model.
5. Original ancestor regression tests still pass.
6. Frozen modern upstream regression still passes untouched.
7. GitHub Actions timing is not interpreted as a performance benchmark.

## What passing P05b would mean

It would mean that our public reconstruction is a credible **correctness oracle** for the joint observable-mask semantics on small cases. It still would not prove equivalence to the unavailable private branch.

The next safe step would then be to port this verified behavior into a separate path on the modern frozen Trellis and differential-test modern-versus-reference before running large BB workloads.
