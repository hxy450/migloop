"""Deterministic first-frame allocation, independent of subject or findings."""


def initial_limits(lengths, frame_size):
    count = len(lengths)
    if count == 1:
        return [min(lengths[0], frame_size)]
    budget = max(40 * count, frame_size - 225 * count)
    # Never reduce an item's prefix below the former equal-share policy.
    floor = budget // count
    limits = [min(size, floor) for size in lengths]
    remaining = budget - sum(limits)
    # Finish short packets first, without changing query/execution/output order.
    for i in sorted(range(count), key=lambda i: (lengths[i], i)):
        need = lengths[i] - limits[i]
        if need <= remaining:
            limits[i] += need
            remaining -= need
    pending = [i for i in range(count) if limits[i] < lengths[i]]
    if pending:
        share, extra = divmod(remaining, len(pending))
        for rank, i in enumerate(pending):
            limits[i] += share + (rank < extra)
    return limits
