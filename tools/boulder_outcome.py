"""Impact categories for the fixed eight-runner demonstration."""

DOWN_IMPULSE = 500.0


def outcome(contact, impulse):
    if not contact:
        return "clear"
    return "down" if impulse >= DOWN_IMPULSE else "graze"


def settle_frame(heights, motion, start):
    candidates = [i for i in range(start, len(heights)) if heights[i] < .40]
    if not candidates:
        raise ValueError("A severe impact has no low pose to hold.")
    return min(candidates, key=lambda i: motion[i])
